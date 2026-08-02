package com.aic.notifications.security;

import jakarta.servlet.FilterChain;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.test.util.ReflectionTestUtils;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

class AdminAuthFilterTest {

    private static final String ADMIN_KEY = "test-admin-key";

    private AdminAuthFilter filter;

    @BeforeEach
    void setUp() {
        filter = new AdminAuthFilter();
        ReflectionTestUtils.setField(filter, "adminApiKey", ADMIN_KEY);
    }

    @Test
    void nonAdminPathIsPassedThroughRegardlessOfHeader() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/notifications");
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain chain = mock(FilterChain.class);

        filter.doFilterInternal(request, response, chain);

        verify(chain).doFilter(request, response);
        assertThat(response.getStatus()).isEqualTo(200);
    }

    @Test
    void adminPathWithCorrectKeyIsPassedThrough() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/admin/fault-injection");
        request.addHeader("X-Admin-Api-Key", ADMIN_KEY);
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain chain = mock(FilterChain.class);

        filter.doFilterInternal(request, response, chain);

        verify(chain).doFilter(request, response);
        assertThat(response.getStatus()).isEqualTo(200);
    }

    @Test
    void adminPathWithMissingKeyIsRejectedWithUnauthorized() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/admin/fault-injection");
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain chain = mock(FilterChain.class);

        filter.doFilterInternal(request, response, chain);

        verify(chain, never()).doFilter(request, response);
        assertThat(response.getStatus()).isEqualTo(401);
        assertThat(response.getContentAsString()).contains("missing or invalid X-Admin-Api-Key header");
    }

    @Test
    void adminPathWithWrongKeyIsRejectedWithUnauthorized() throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest("DELETE", "/admin/fault-injection");
        request.addHeader("X-Admin-Api-Key", "wrong-key");
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain chain = mock(FilterChain.class);

        filter.doFilterInternal(request, response, chain);

        verify(chain, never()).doFilter(request, response);
        assertThat(response.getStatus()).isEqualTo(401);
    }
}
