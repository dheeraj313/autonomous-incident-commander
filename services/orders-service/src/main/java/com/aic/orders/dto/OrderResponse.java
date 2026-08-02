package com.aic.orders.dto;

import com.aic.orders.model.Order;

import java.time.Instant;

public record OrderResponse(Long id, String username, String item, int quantity, String status, Instant createdAt) {
    public static OrderResponse from(Order order) {
        return new OrderResponse(order.getId(), order.getUsername(), order.getItem(),
                order.getQuantity(), order.getStatus(), order.getCreatedAt());
    }
}
