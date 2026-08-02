package com.aic.inventory.dto;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record ReserveRequest(@NotBlank String item, @Min(1) int quantity) {
}
