package com.aic.orders.circuitbreaker;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.util.HashMap;
import java.util.Map;

/**
 * Minimal Redis-backed circuit breaker guarding orders-service's calls to
 * downstream services (inventory-service, payments-service).
 *
 * Keys:
 *  - circuit-breaker:{service}:open      presence = breaker is open (fail-fast)
 *  - circuit-breaker:{service}:failures  rolling failure counter within failureWindow
 *
 * Automatic tripping: {@link #recordFailure(String)} increments the failure
 * counter (TTL-bounded window) and opens the breaker once failureThreshold is
 * reached, for openDuration, after which it auto-resets to half-open (i.e.
 * the next call is allowed through again). Admin endpoints allow manually
 * tripping/resetting a breaker to demo the future remediation engine's
 * "trip circuit breaker" action.
 */
@Service
public class CircuitBreakerService {

    private final StringRedisTemplate redisTemplate;
    private final int failureThreshold;
    private final Duration failureWindow;
    private final Duration openDuration;

    public CircuitBreakerService(StringRedisTemplate redisTemplate,
                                  @Value("${aic.circuit-breaker.failure-threshold:3}") int failureThreshold,
                                  @Value("${aic.circuit-breaker.failure-window-seconds:30}") long failureWindowSeconds,
                                  @Value("${aic.circuit-breaker.open-seconds:30}") long openSeconds) {
        this.redisTemplate = redisTemplate;
        this.failureThreshold = failureThreshold;
        this.failureWindow = Duration.ofSeconds(failureWindowSeconds);
        this.openDuration = Duration.ofSeconds(openSeconds);
    }

    private String openKey(String service) {
        return "circuit-breaker:" + service + ":open";
    }

    private String failuresKey(String service) {
        return "circuit-breaker:" + service + ":failures";
    }

    public boolean isOpen(String service) {
        return Boolean.TRUE.equals(redisTemplate.hasKey(openKey(service)));
    }

    public void recordSuccess(String service) {
        redisTemplate.delete(failuresKey(service));
    }

    public void recordFailure(String service) {
        Long count = redisTemplate.opsForValue().increment(failuresKey(service));
        if (count != null && count == 1L) {
            redisTemplate.expire(failuresKey(service), failureWindow);
        }
        if (count != null && count >= failureThreshold) {
            trip(service, openDuration.toSeconds());
        }
    }

    public void trip(String service, long ttlSeconds) {
        redisTemplate.opsForValue().set(openKey(service), "true", Duration.ofSeconds(ttlSeconds));
    }

    public void reset(String service) {
        redisTemplate.delete(openKey(service));
        redisTemplate.delete(failuresKey(service));
    }

    public Map<String, Object> status(String service) {
        Long ttl = redisTemplate.getExpire(openKey(service));
        Map<String, Object> result = new HashMap<>();
        result.put("service", service);
        result.put("open", isOpen(service));
        result.put("ttlSeconds", ttl == null ? -1 : ttl);
        return result;
    }
}
