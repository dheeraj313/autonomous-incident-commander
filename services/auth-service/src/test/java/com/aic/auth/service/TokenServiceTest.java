package com.aic.auth.service;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;

import java.time.Duration;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.startsWith;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class TokenServiceTest {

    private StringRedisTemplate redisTemplate;
    private ValueOperations<String, String> valueOperations;
    private TokenService tokenService;

    @BeforeEach
    void setUp() {
        redisTemplate = mock(StringRedisTemplate.class);
        @SuppressWarnings("unchecked")
        ValueOperations<String, String> ops = mock(ValueOperations.class);
        valueOperations = ops;
        when(redisTemplate.opsForValue()).thenReturn(valueOperations);
        tokenService = new TokenService(redisTemplate);
    }

    @Test
    void issueTokenStoresUsernameUnderRandomTokenKeyWithTwoHourTtl() {
        String token = tokenService.issueToken("alice");

        assertThat(token).isNotBlank();
        assertThat(UUID.fromString(token)).isNotNull(); // must be a valid UUID

        verify(valueOperations).set(
                eq("auth-service:token:" + token),
                eq("alice"),
                eq(Duration.ofHours(2)));
    }

    @Test
    void issueTokenReturnsADifferentTokenEachCall() {
        String first = tokenService.issueToken("alice");
        String second = tokenService.issueToken("alice");

        assertThat(first).isNotEqualTo(second);
    }

    @Test
    void resolveUsernameReturnsUsernameWhenTokenExists() {
        when(redisTemplate.opsForValue()).thenReturn(valueOperations);
        when(valueOperations.get(startsWith("auth-service:token:"))).thenReturn("alice");

        Optional<String> resolved = tokenService.resolveUsername("some-token");

        assertThat(resolved).contains("alice");
    }

    @Test
    void resolveUsernameReturnsEmptyWhenTokenUnknownOrExpired() {
        when(valueOperations.get(any())).thenReturn(null);

        Optional<String> resolved = tokenService.resolveUsername("unknown-token");

        assertThat(resolved).isEmpty();
    }
}
