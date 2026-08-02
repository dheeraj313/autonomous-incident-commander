package com.aic.orders.service;

import com.aic.orders.circuitbreaker.CircuitBreakerService;
import com.aic.orders.client.AuthClient;
import com.aic.orders.client.InventoryClient;
import com.aic.orders.client.PaymentsClient;
import com.aic.orders.dto.CreateOrderRequest;
import com.aic.orders.kafka.OrderEventPublisher;
import com.aic.orders.model.Order;
import com.aic.orders.repository.OrderRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import java.math.BigDecimal;

@Service
public class OrderService {

    private static final String INVENTORY_SERVICE = "inventory-service";
    private static final String PAYMENTS_SERVICE = "payments-service";

    private final OrderRepository orderRepository;
    private final AuthClient authClient;
    private final InventoryClient inventoryClient;
    private final PaymentsClient paymentsClient;
    private final CircuitBreakerService circuitBreakerService;
    private final OrderEventPublisher eventPublisher;
    private final BigDecimal unitPrice;

    public OrderService(OrderRepository orderRepository, AuthClient authClient, InventoryClient inventoryClient,
                         PaymentsClient paymentsClient, CircuitBreakerService circuitBreakerService,
                         OrderEventPublisher eventPublisher,
                         @Value("${aic.orders.unit-price}") BigDecimal unitPrice) {
        this.orderRepository = orderRepository;
        this.authClient = authClient;
        this.inventoryClient = inventoryClient;
        this.paymentsClient = paymentsClient;
        this.circuitBreakerService = circuitBreakerService;
        this.eventPublisher = eventPublisher;
        this.unitPrice = unitPrice;
    }

    /**
     * Orchestrates order creation as a simple (non-compensating) saga:
     * validate token -> persist order -> reserve inventory -> charge payment.
     * Each downstream step is guarded by a circuit breaker: if the breaker for
     * that service is open, the step is skipped (fail-fast) instead of
     * attempting a call known to be failing. This is a deliberate demo
     * simplification: on partial failure the order is left in a terminal
     * failure status rather than rolling back the inventory reservation.
     */
    public Order createOrder(String bearerToken, CreateOrderRequest request) {
        AuthClient.ValidationResult validation = authClient.validate(bearerToken);
        if (!validation.valid()) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "invalid or expired token");
        }

        Order order = new Order(validation.username(), request.item(), request.quantity());
        orderRepository.save(order);
        eventPublisher.publish(order.getId(), order.getUsername(), "ORDER_CREATED");

        reserveInventory(order);
        if ("INVENTORY_RESERVED".equals(order.getStatus())) {
            chargePayment(order);
        }

        orderRepository.save(order);
        eventPublisher.publish(order.getId(), order.getUsername(), "ORDER_" + order.getStatus());
        return order;
    }

    private void reserveInventory(Order order) {
        if (circuitBreakerService.isOpen(INVENTORY_SERVICE)) {
            order.setStatus("INVENTORY_SKIPPED_CIRCUIT_OPEN");
            return;
        }
        try {
            inventoryClient.reserve(order.getItem(), order.getQuantity());
            circuitBreakerService.recordSuccess(INVENTORY_SERVICE);
            order.setStatus("INVENTORY_RESERVED");
        } catch (ResponseStatusException e) {
            if (e.getStatusCode() != HttpStatus.CONFLICT) {
                // Infra failure (timeout, connection error, 5xx) counts toward tripping
                // the breaker. A 409 is a legitimate business rejection (out of stock)
                // and should not be treated as inventory-service being unhealthy.
                circuitBreakerService.recordFailure(INVENTORY_SERVICE);
            }
            order.setStatus("INVENTORY_FAILED");
        } catch (Exception e) {
            circuitBreakerService.recordFailure(INVENTORY_SERVICE);
            order.setStatus("INVENTORY_FAILED");
        }
    }

    private void chargePayment(Order order) {
        if (circuitBreakerService.isOpen(PAYMENTS_SERVICE)) {
            order.setStatus("PAYMENT_SKIPPED_CIRCUIT_OPEN");
            return;
        }
        BigDecimal amount = unitPrice.multiply(BigDecimal.valueOf(order.getQuantity()));
        try {
            paymentsClient.charge(order.getId(), order.getUsername(), amount);
            circuitBreakerService.recordSuccess(PAYMENTS_SERVICE);
            order.setStatus("COMPLETED");
        } catch (Exception e) {
            circuitBreakerService.recordFailure(PAYMENTS_SERVICE);
            order.setStatus("PAYMENT_FAILED");
        }
    }

    public Order getOrder(Long id) {
        return orderRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "order not found"));
    }
}

