package com.aic.auth.service;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.util.Optional;
import java.util.UUID;

/**
 * Minimal opaque-token session store backed by Redis (token -> username),
 * intentionally simple (no JWT) to keep the sandbox focused on the
 * observability/remediation story rather than auth mechanics.
 */
@Service
public class TokenService {

    private static final String TOKEN_KEY_PREFIX = "auth-service:token:";
    private static final Duration TOKEN_TTL = Duration.ofHours(2);

    private final StringRedisTemplate redisTemplate;

    public TokenService(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    public String issueToken(String username) {
        String token = UUID.randomUUID().toString();
        redisTemplate.opsForValue().set(TOKEN_KEY_PREFIX + token, username, TOKEN_TTL);
        return token;
    }

    public Optional<String> resolveUsername(String token) {
        return Optional.ofNullable(redisTemplate.opsForValue().get(TOKEN_KEY_PREFIX + token));
    }
}
