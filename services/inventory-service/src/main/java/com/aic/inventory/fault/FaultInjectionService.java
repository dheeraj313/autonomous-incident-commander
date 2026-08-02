package com.aic.inventory.fault;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class FaultInjectionService {

    private static final String LATENCY_KEY = "fault-injection:inventory-service:latency-ms";
    private static final String ERROR_RATE_KEY = "fault-injection:inventory-service:error-rate";

    private final StringRedisTemplate redisTemplate;

    public FaultInjectionService(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    public void setLatencyMs(int latencyMs) {
        redisTemplate.opsForValue().set(LATENCY_KEY, String.valueOf(latencyMs));
    }

    public void setErrorRate(double errorRate) {
        redisTemplate.opsForValue().set(ERROR_RATE_KEY, String.valueOf(errorRate));
    }

    public void clear() {
        redisTemplate.delete(LATENCY_KEY);
        redisTemplate.delete(ERROR_RATE_KEY);
    }

    public int getLatencyMs() {
        String value = redisTemplate.opsForValue().get(LATENCY_KEY);
        return value == null ? 0 : Integer.parseInt(value);
    }

    public double getErrorRate() {
        String value = redisTemplate.opsForValue().get(ERROR_RATE_KEY);
        return value == null ? 0.0 : Double.parseDouble(value);
    }

    public void apply() {
        int latencyMs = getLatencyMs();
        if (latencyMs > 0) {
            try {
                Thread.sleep(latencyMs);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
        double errorRate = getErrorRate();
        if (errorRate > 0 && Math.random() < errorRate) {
            throw new InjectedFaultException("Injected fault in inventory-service");
        }
    }
}
