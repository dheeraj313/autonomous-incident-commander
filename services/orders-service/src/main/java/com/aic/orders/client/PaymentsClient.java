package com.aic.orders.client;

import org.springframework.stereotype.Component;
import org.springframework.http.HttpStatus;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;

import java.math.BigDecimal;

/**
 * Thin client to payments-service. Any failure here (this sandbox has no real
 * payment provider, so failures are only ever infra/fault-injection related)
 * is treated as an infrastructure failure that counts toward tripping the
 * circuit breaker.
 */
@Component
public class PaymentsClient {

    private final RestClient restClient;

    public PaymentsClient(RestClient paymentsServiceRestClient) {
        this.restClient = paymentsServiceRestClient;
    }

    public record ChargeRequest(Long orderId, String username, BigDecimal amount) {
    }

    public record ChargeResult(Long id, Long orderId, String username, BigDecimal amount, String status) {
    }

    public ChargeResult charge(Long orderId, String username, BigDecimal amount) {
        try {
            return restClient.post()
                    .uri("/api/payments/charge")
                    .body(new ChargeRequest(orderId, username, amount))
                    .retrieve()
                    .body(ChargeResult.class);
        } catch (Exception e) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                    "payments-service unavailable: " + e.getMessage());
        }
    }
}
