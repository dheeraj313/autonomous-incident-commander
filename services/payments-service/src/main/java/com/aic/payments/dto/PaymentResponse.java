package com.aic.payments.dto;

import com.aic.payments.model.Payment;

import java.math.BigDecimal;
import java.time.Instant;

public record PaymentResponse(Long id, Long orderId, String username, BigDecimal amount, String status,
                               Instant createdAt) {
    public static PaymentResponse from(Payment payment) {
        return new PaymentResponse(payment.getId(), payment.getOrderId(), payment.getUsername(),
                payment.getAmount(), payment.getStatus(), payment.getCreatedAt());
    }
}
