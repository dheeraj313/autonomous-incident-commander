package com.aic.auth.dto;

public record TokenValidationResponse(boolean valid, String username) {
}
