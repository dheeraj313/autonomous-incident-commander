package com.aic.orders.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * Guards every /admin/** endpoint (fault injection, circuit-breaker control)
 * with a shared secret header. These endpoints can disrupt the service and
 * previously had no authentication at all. This is not a real auth system
 * (no users/roles/sessions) - just a minimal guard against unauthenticated
 * abuse, consistent with the same header/env-var convention used across
 * every service in this stack.
 */
@Component
public class AdminAuthFilter extends OncePerRequestFilter {

    @Value("${aic.admin.api-key}")
    private String adminApiKey;

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain)
            throws ServletException, IOException {
        if (request.getRequestURI().startsWith("/admin/")) {
            String provided = request.getHeader("X-Admin-Api-Key");
            if (provided == null || !provided.equals(adminApiKey)) {
                response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                response.setContentType("application/json");
                response.getWriter().write("{\"error\":\"missing or invalid X-Admin-Api-Key header\"}");
                return;
            }
        }
        filterChain.doFilter(request, response);
    }
}
