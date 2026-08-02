package com.aic.orders.circuitbreaker;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;

import java.time.Duration;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class CircuitBreakerServiceTest {

    private static final String SERVICE = "inventory-service";

    private StringRedisTemplate redisTemplate;
    private ValueOperations<String, String> valueOperations;
    private CircuitBreakerService circuitBreakerService;

    @BeforeEach
    void setUp() {
        redisTemplate = mock(StringRedisTemplate.class);
        @SuppressWarnings("unchecked")
        ValueOperations<String, String> ops = mock(ValueOperations.class);
        valueOperations = ops;
        when(redisTemplate.opsForValue()).thenReturn(valueOperations);
        // threshold=3, failureWindow=30s, openDuration=60s
        circuitBreakerService = new CircuitBreakerService(redisTemplate, 3, 30, 60);
    }

    @Test
    void isOpenReflectsPresenceOfOpenKey() {
        when(redisTemplate.hasKey("circuit-breaker:" + SERVICE + ":open")).thenReturn(true);
        assertThat(circuitBreakerService.isOpen(SERVICE)).isTrue();

        when(redisTemplate.hasKey("circuit-breaker:" + SERVICE + ":open")).thenReturn(false);
        assertThat(circuitBreakerService.isOpen(SERVICE)).isFalse();
    }

    @Test
    void recordSuccessClearsFailureCounter() {
        circuitBreakerService.recordSuccess(SERVICE);

        verify(redisTemplate).delete("circuit-breaker:" + SERVICE + ":failures");
    }

    @Test
    void firstFailureSetsExpiryOnCounterButDoesNotTripBreaker() {
        when(valueOperations.increment("circuit-breaker:" + SERVICE + ":failures")).thenReturn(1L);

        circuitBreakerService.recordFailure(SERVICE);

        verify(redisTemplate).expire(eq("circuit-breaker:" + SERVICE + ":failures"), eq(Duration.ofSeconds(30)));
        verify(valueOperations, never()).set(eq("circuit-breaker:" + SERVICE + ":open"), eq("true"), any(Duration.class));
    }

    @Test
    void reachingFailureThresholdTripsTheBreaker() {
        when(valueOperations.increment("circuit-breaker:" + SERVICE + ":failures")).thenReturn(3L);

        circuitBreakerService.recordFailure(SERVICE);

        verify(valueOperations).set(
                eq("circuit-breaker:" + SERVICE + ":open"),
                eq("true"),
                eq(Duration.ofSeconds(60)));
    }

    @Test
    void manualTripOpensBreakerForGivenTtl() {
        circuitBreakerService.trip(SERVICE, 45);

        verify(valueOperations).set(
                eq("circuit-breaker:" + SERVICE + ":open"),
                eq("true"),
                eq(Duration.ofSeconds(45)));
    }

    @Test
    void resetClearsBothOpenAndFailureKeys() {
        circuitBreakerService.reset(SERVICE);

        verify(redisTemplate).delete("circuit-breaker:" + SERVICE + ":open");
        verify(redisTemplate).delete("circuit-breaker:" + SERVICE + ":failures");
    }

    @Test
    void statusReportsServiceOpenStateAndTtl() {
        when(redisTemplate.hasKey("circuit-breaker:" + SERVICE + ":open")).thenReturn(true);
        when(redisTemplate.getExpire("circuit-breaker:" + SERVICE + ":open")).thenReturn(42L);

        Map<String, Object> status = circuitBreakerService.status(SERVICE);

        assertThat(status.get("service")).isEqualTo(SERVICE);
        assertThat(status.get("open")).isEqualTo(true);
        assertThat(status.get("ttlSeconds")).isEqualTo(42L);
    }

    @Test
    void statusReportsMinusOneTtlWhenNotOpen() {
        when(redisTemplate.hasKey("circuit-breaker:" + SERVICE + ":open")).thenReturn(false);
        when(redisTemplate.getExpire("circuit-breaker:" + SERVICE + ":open")).thenReturn(null);

        Map<String, Object> status = circuitBreakerService.status(SERVICE);

        assertThat(status.get("open")).isEqualTo(false);
        assertThat(status.get("ttlSeconds")).isEqualTo(-1L);
    }
}
