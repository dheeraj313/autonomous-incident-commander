package com.aic.payments.dto;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import java.math.BigDecimal;

public record ChargeRequest(
        @NotNull Long orderId,
        @NotBlank String username,
        @NotNull @DecimalMin("0.01") BigDecimal amount) {
}
