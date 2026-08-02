package com.aic.orders.client;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;

/**
 * Thin client to auth-service. This inter-service call is what makes
 * auth-service a real upstream dependency in the trace-derived service graph
 * (orders -> auth), which the causal-analysis engine will use later.
 */
@Component
public class AuthClient {

    private final RestClient restClient;

    public AuthClient(RestClient authServiceRestClient) {
        this.restClient = authServiceRestClient;
    }

    public record ValidationResult(boolean valid, String username) {
    }

    public ValidationResult validate(String bearerToken) {
        try {
            var response = restClient.get()
                    .uri("/api/auth/validate")
                    .header("Authorization", bearerToken)
                    .retrieve()
                    .body(java.util.Map.class);
            boolean valid = Boolean.TRUE.equals(response.get("valid"));
            String username = (String) response.get("username");
            return new ValidationResult(valid, username);
        } catch (Exception e) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                    "auth-service unavailable: " + e.getMessage());
        }
    }
}
