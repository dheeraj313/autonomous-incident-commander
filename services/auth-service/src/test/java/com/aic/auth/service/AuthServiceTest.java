package com.aic.auth.service;

import com.aic.auth.dto.AuthResponse;
import com.aic.auth.dto.LoginRequest;
import com.aic.auth.dto.RegisterRequest;
import com.aic.auth.dto.TokenValidationResponse;
import com.aic.auth.kafka.AuthEventPublisher;
import com.aic.auth.model.User;
import com.aic.auth.repository.UserRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.web.server.ResponseStatusException;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AuthServiceTest {

    private static final BCryptPasswordEncoder ENCODER = new BCryptPasswordEncoder();

    private UserRepository userRepository;
    private TokenService tokenService;
    private AuthEventPublisher eventPublisher;
    private AuthService authService;

    @BeforeEach
    void setUp() {
        userRepository = mock(UserRepository.class);
        tokenService = mock(TokenService.class);
        eventPublisher = mock(AuthEventPublisher.class);
        authService = new AuthService(userRepository, tokenService, eventPublisher);
    }

    @Test
    void registerSavesNewUserPublishesEventAndIssuesToken() {
        when(userRepository.existsByUsername("alice")).thenReturn(false);
        when(tokenService.issueToken("alice")).thenReturn("token-123");

        AuthResponse response = authService.register(new RegisterRequest("alice", "password1"));

        assertThat(response.username()).isEqualTo("alice");
        assertThat(response.token()).isEqualTo("token-123");
        verify(userRepository).save(any(User.class));
        verify(eventPublisher).publish("alice", "USER_REGISTERED");
    }

    @Test
    void registerRejectsDuplicateUsernameWithConflict() {
        when(userRepository.existsByUsername("alice")).thenReturn(true);

        assertThatThrownBy(() -> authService.register(new RegisterRequest("alice", "password1")))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("username already exists");

        verify(userRepository, never()).save(any());
        verify(eventPublisher, never()).publish(any(), any());
    }

    @Test
    void loginWithCorrectPasswordIssuesToken() {
        User user = new User("alice", ENCODER.encode("password1"));
        when(userRepository.findByUsername("alice")).thenReturn(Optional.of(user));
        when(tokenService.issueToken("alice")).thenReturn("token-456");

        AuthResponse response = authService.login(new LoginRequest("alice", "password1"));

        assertThat(response.username()).isEqualTo("alice");
        assertThat(response.token()).isEqualTo("token-456");
        verify(eventPublisher).publish("alice", "USER_LOGIN");
    }

    @Test
    void loginWithWrongPasswordIsUnauthorized() {
        User user = new User("alice", ENCODER.encode("password1"));
        when(userRepository.findByUsername("alice")).thenReturn(Optional.of(user));

        assertThatThrownBy(() -> authService.login(new LoginRequest("alice", "wrong-password")))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("invalid credentials");

        verify(tokenService, never()).issueToken(any());
    }

    @Test
    void loginWithUnknownUsernameIsUnauthorized() {
        when(userRepository.findByUsername("ghost")).thenReturn(Optional.empty());

        assertThatThrownBy(() -> authService.login(new LoginRequest("ghost", "whatever")))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("invalid credentials");
    }

    @Test
    void validateDelegatesToTokenServiceAndReportsValidWhenFound() {
        when(tokenService.resolveUsername("tok")).thenReturn(Optional.of("alice"));

        TokenValidationResponse response = authService.validate("tok");

        assertThat(response.valid()).isTrue();
        assertThat(response.username()).isEqualTo("alice");
    }

    @Test
    void validateReportsInvalidWhenTokenNotFound() {
        when(tokenService.resolveUsername("tok")).thenReturn(Optional.empty());

        TokenValidationResponse response = authService.validate("tok");

        assertThat(response.valid()).isFalse();
        assertThat(response.username()).isNull();
    }
}
