package com.aic.auth.controller;

import com.aic.auth.dto.AuthResponse;
import com.aic.auth.dto.LoginRequest;
import com.aic.auth.dto.RegisterRequest;
import com.aic.auth.dto.TokenValidationResponse;
import com.aic.auth.fault.FaultInjectionService;
import com.aic.auth.service.AuthService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/auth")
public class AuthController {

    private final AuthService authService;
    private final FaultInjectionService faultInjectionService;

    public AuthController(AuthService authService, FaultInjectionService faultInjectionService) {
        this.authService = authService;
        this.faultInjectionService = faultInjectionService;
    }

    @PostMapping("/register")
    public AuthResponse register(@Valid @RequestBody RegisterRequest request) {
        faultInjectionService.apply();
        return authService.register(request);
    }

    @PostMapping("/login")
    public AuthResponse login(@Valid @RequestBody LoginRequest request) {
        faultInjectionService.apply();
        return authService.login(request);
    }

    @GetMapping("/validate")
    public TokenValidationResponse validate(@RequestHeader("Authorization") String authorizationHeader) {
        faultInjectionService.apply();
        String token = authorizationHeader.replaceFirst("(?i)^Bearer ", "");
        return authService.validate(token);
    }
}
