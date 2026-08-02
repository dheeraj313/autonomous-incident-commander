package com.aic.orders.service;

import com.aic.orders.circuitbreaker.CircuitBreakerService;
import com.aic.orders.client.AuthClient;
import com.aic.orders.client.InventoryClient;
import com.aic.orders.client.PaymentsClient;
import com.aic.orders.dto.CreateOrderRequest;
import com.aic.orders.kafka.OrderEventPublisher;
import com.aic.orders.model.Order;
import com.aic.orders.repository.OrderRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import java.math.BigDecimal;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class OrderServiceTest {

    private OrderRepository orderRepository;
    private AuthClient authClient;
    private InventoryClient inventoryClient;
    private PaymentsClient paymentsClient;
    private CircuitBreakerService circuitBreakerService;
    private OrderEventPublisher eventPublisher;
    private OrderService orderService;

    @BeforeEach
    void setUp() {
        orderRepository = mock(OrderRepository.class);
        authClient = mock(AuthClient.class);
        inventoryClient = mock(InventoryClient.class);
        paymentsClient = mock(PaymentsClient.class);
        circuitBreakerService = mock(CircuitBreakerService.class);
        eventPublisher = mock(OrderEventPublisher.class);
        orderService = new OrderService(orderRepository, authClient, inventoryClient, paymentsClient,
                circuitBreakerService, eventPublisher, BigDecimal.TEN);

        when(authClient.validate(anyString())).thenReturn(new AuthClient.ValidationResult(true, "alice"));
    }

    @Test
    void rejectsOrderWhenTokenIsInvalid() {
        when(authClient.validate(anyString())).thenReturn(new AuthClient.ValidationResult(false, null));

        assertThatThrownBy(() -> orderService.createOrder("Bearer bad-token", new CreateOrderRequest("widget", 1)))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("invalid or expired token");

        verify(orderRepository, never()).save(any());
    }

    @Test
    void happyPathReservesInventoryAndChargesPaymentToCompletion() {
        when(inventoryClient.reserve("widget", 2)).thenReturn(new InventoryClient.ReserveResult("widget", 8));
        when(paymentsClient.charge(any(), eq("alice"), eq(BigDecimal.valueOf(20))))
                .thenReturn(new PaymentsClient.ChargeResult(1L, 1L, "alice", BigDecimal.valueOf(20), "CHARGED"));

        Order order = orderService.createOrder("Bearer good-token", new CreateOrderRequest("widget", 2));

        assertThat(order.getStatus()).isEqualTo("COMPLETED");
        verify(circuitBreakerService).recordSuccess("inventory-service");
        verify(circuitBreakerService).recordSuccess("payments-service");
        verify(eventPublisher).publish(any(), eq("alice"), eq("ORDER_CREATED"));
        verify(eventPublisher).publish(any(), eq("alice"), eq("ORDER_COMPLETED"));
    }

    @Test
    void insufficientStockDoesNotTripBreakerAndSkipsPayment() {
        when(inventoryClient.reserve("widget", 999))
                .thenThrow(new ResponseStatusException(HttpStatus.CONFLICT, "insufficient stock"));

        Order order = orderService.createOrder("Bearer good-token", new CreateOrderRequest("widget", 999));

        assertThat(order.getStatus()).isEqualTo("INVENTORY_FAILED");
        // A 409 is a legitimate business rejection, not an infra failure - must not trip the breaker.
        verify(circuitBreakerService, never()).recordFailure("inventory-service");
        verify(paymentsClient, never()).charge(any(), anyString(), any());
    }

    @Test
    void inventoryInfrastructureFailureTripsBreakerAndSkipsPayment() {
        when(inventoryClient.reserve("widget", 1))
                .thenThrow(new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "inventory-service down"));

        Order order = orderService.createOrder("Bearer good-token", new CreateOrderRequest("widget", 1));

        assertThat(order.getStatus()).isEqualTo("INVENTORY_FAILED");
        verify(circuitBreakerService).recordFailure("inventory-service");
        verify(paymentsClient, never()).charge(any(), anyString(), any());
    }

    @Test
    void openInventoryBreakerSkipsInventoryCallEntirely() {
        when(circuitBreakerService.isOpen("inventory-service")).thenReturn(true);

        Order order = orderService.createOrder("Bearer good-token", new CreateOrderRequest("widget", 1));

        assertThat(order.getStatus()).isEqualTo("INVENTORY_SKIPPED_CIRCUIT_OPEN");
        verify(inventoryClient, never()).reserve(anyString(), anyInt());
    }

    @Test
    void paymentFailureAfterSuccessfulReservationTripsPaymentsBreaker() {
        when(inventoryClient.reserve("widget", 1)).thenReturn(new InventoryClient.ReserveResult("widget", 9));
        when(paymentsClient.charge(any(), anyString(), any())).thenThrow(new RuntimeException("payments-service down"));

        Order order = orderService.createOrder("Bearer good-token", new CreateOrderRequest("widget", 1));

        assertThat(order.getStatus()).isEqualTo("PAYMENT_FAILED");
        verify(circuitBreakerService).recordSuccess("inventory-service");
        verify(circuitBreakerService).recordFailure("payments-service");
    }

    @Test
    void openPaymentsBreakerSkipsPaymentCallAfterSuccessfulReservation() {
        when(inventoryClient.reserve("widget", 1)).thenReturn(new InventoryClient.ReserveResult("widget", 9));
        when(circuitBreakerService.isOpen("payments-service")).thenReturn(true);

        Order order = orderService.createOrder("Bearer good-token", new CreateOrderRequest("widget", 1));

        assertThat(order.getStatus()).isEqualTo("PAYMENT_SKIPPED_CIRCUIT_OPEN");
        verify(paymentsClient, never()).charge(any(), anyString(), any());
    }

    @Test
    void getOrderReturnsOrderWhenFound() {
        Order order = new Order("alice", "widget", 1);
        when(orderRepository.findById(1L)).thenReturn(java.util.Optional.of(order));

        assertThat(orderService.getOrder(1L)).isSameAs(order);
    }

    @Test
    void getOrderThrowsNotFoundWhenMissing() {
        when(orderRepository.findById(anyLong())).thenReturn(java.util.Optional.empty());

        assertThatThrownBy(() -> orderService.getOrder(99L))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("order not found");
    }
}
