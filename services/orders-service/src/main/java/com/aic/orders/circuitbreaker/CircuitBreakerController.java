package com.aic.orders.circuitbreaker;

import jakarta.validation.constraints.Min;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/admin/circuit-breaker")
public class CircuitBreakerController {

    private final CircuitBreakerService circuitBreakerService;

    public CircuitBreakerController(CircuitBreakerService circuitBreakerService) {
        this.circuitBreakerService = circuitBreakerService;
    }

    public record TripRequest(@Min(1) Long ttlSeconds) {
    }

    @GetMapping("/{service}")
    public Map<String, Object> status(@PathVariable String service) {
        return circuitBreakerService.status(service);
    }

    @PostMapping("/{service}/trip")
    public Map<String, Object> trip(@PathVariable String service, @RequestBody(required = false) TripRequest request) {
        long ttlSeconds = (request != null && request.ttlSeconds() != null) ? request.ttlSeconds() : 30;
        circuitBreakerService.trip(service, ttlSeconds);
        return circuitBreakerService.status(service);
    }

    @PostMapping("/{service}/reset")
    public Map<String, Object> reset(@PathVariable String service) {
        circuitBreakerService.reset(service);
        return circuitBreakerService.status(service);
    }
}
