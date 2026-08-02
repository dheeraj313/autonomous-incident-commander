package com.aic.orders.client;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;

/**
 * Thin client to inventory-service. Distinguishes a business-level rejection
 * (409 insufficient stock) from an infrastructure failure (connection error,
 * 5xx, timeout) so the caller can decide whether to trip the circuit breaker.
 */
@Component
public class InventoryClient {

    private final RestClient restClient;

    public InventoryClient(RestClient inventoryServiceRestClient) {
        this.restClient = inventoryServiceRestClient;
    }

    public record ReserveRequest(String item, int quantity) {
    }

    public record ReserveResult(String item, int quantityAvailable) {
    }

    public ReserveResult reserve(String item, int quantity) {
        try {
            return restClient.post()
                    .uri("/api/inventory/reserve")
                    .body(new ReserveRequest(item, quantity))
                    .retrieve()
                    .body(ReserveResult.class);
        } catch (HttpClientErrorException.Conflict e) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "insufficient stock: " + e.getMessage());
        } catch (Exception e) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                    "inventory-service unavailable: " + e.getMessage());
        }
    }
}
