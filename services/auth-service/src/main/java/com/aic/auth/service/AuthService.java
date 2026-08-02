package com.aic.auth.service;

import com.aic.auth.dto.AuthResponse;
import com.aic.auth.dto.LoginRequest;
import com.aic.auth.dto.RegisterRequest;
import com.aic.auth.dto.TokenValidationResponse;
import com.aic.auth.kafka.AuthEventPublisher;
import com.aic.auth.model.User;
import com.aic.auth.repository.UserRepository;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class AuthService {

    private final UserRepository userRepository;
    private final TokenService tokenService;
    private final AuthEventPublisher eventPublisher;
    private final BCryptPasswordEncoder passwordEncoder = new BCryptPasswordEncoder();

    public AuthService(UserRepository userRepository, TokenService tokenService, AuthEventPublisher eventPublisher) {
        this.userRepository = userRepository;
        this.tokenService = tokenService;
        this.eventPublisher = eventPublisher;
    }

    public AuthResponse register(RegisterRequest request) {
        if (userRepository.existsByUsername(request.username())) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "username already exists");
        }
        User user = new User(request.username(), passwordEncoder.encode(request.password()));
        userRepository.save(user);
        eventPublisher.publish(user.getUsername(), "USER_REGISTERED");
        String token = tokenService.issueToken(user.getUsername());
        return new AuthResponse(user.getUsername(), token);
    }

    public AuthResponse login(LoginRequest request) {
        User user = userRepository.findByUsername(request.username())
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.UNAUTHORIZED, "invalid credentials"));
        if (!passwordEncoder.matches(request.password(), user.getPasswordHash())) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "invalid credentials");
        }
        eventPublisher.publish(user.getUsername(), "USER_LOGIN");
        String token = tokenService.issueToken(user.getUsername());
        return new AuthResponse(user.getUsername(), token);
    }

    public TokenValidationResponse validate(String token) {
        return tokenService.resolveUsername(token)
                .map(username -> new TokenValidationResponse(true, username))
                .orElseGet(() -> new TokenValidationResponse(false, null));
    }
}
