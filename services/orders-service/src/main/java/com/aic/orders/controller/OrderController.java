package com.aic.orders.controller;

import com.aic.orders.dto.CreateOrderRequest;
import com.aic.orders.dto.OrderResponse;
import com.aic.orders.fault.FaultInjectionService;
import com.aic.orders.model.Order;
import com.aic.orders.service.OrderService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Set;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    // Terminal statuses where the order record was saved but the request did
    // NOT actually complete successfully from the caller's point of view - a
    // downstream dependency failed or was skipped because its circuit breaker
    // was open. Found during Phase 7 chaos testing: this endpoint previously
    // always returned 200 even for these statuses, so a failing/circuit-open
    // downstream service never showed up in orders-service's own HTTP error
    // rate, hiding the failure from causal-analysis-engine's anomaly
    // detection (which only looks at outcome=SERVER_ERROR responses).
    private static final Set<String> FAILED_STATUSES = Set.of(
            "INVENTORY_FAILED", "INVENTORY_SKIPPED_CIRCUIT_OPEN",
            "PAYMENT_FAILED", "PAYMENT_SKIPPED_CIRCUIT_OPEN");

    private final OrderService orderService;
    private final FaultInjectionService faultInjectionService;

    public OrderController(OrderService orderService, FaultInjectionService faultInjectionService) {
        this.orderService = orderService;
        this.faultInjectionService = faultInjectionService;
    }

    @PostMapping
    public ResponseEntity<OrderResponse> createOrder(@RequestHeader("Authorization") String authorizationHeader,
                                                       @Valid @RequestBody CreateOrderRequest request) {
        faultInjectionService.apply();
        Order order = orderService.createOrder(authorizationHeader, request);
        HttpStatus status = FAILED_STATUSES.contains(order.getStatus()) ? HttpStatus.BAD_GATEWAY : HttpStatus.OK;
        return ResponseEntity.status(status).body(OrderResponse.from(order));
    }

    @GetMapping("/{id}")
    public OrderResponse getOrder(@PathVariable Long id) {
        faultInjectionService.apply();
        return OrderResponse.from(orderService.getOrder(id));
    }
}

