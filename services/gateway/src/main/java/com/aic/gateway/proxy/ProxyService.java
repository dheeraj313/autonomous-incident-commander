package com.aic.gateway.proxy;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

import java.io.IOException;
import java.util.Enumeration;
import java.util.Set;

/**
 * Minimal reverse-proxy forwarder: preserves method, path, query string,
 * headers and body, and passes the downstream status code straight through
 * (including 4xx/5xx and injected-fault 503s) instead of throwing, so the
 * gateway behaves like a transparent hop in the trace/service graph.
 */
@Service
public class ProxyService {

    // Hop-by-hop headers that must not be blindly forwarded between hops;
    // letting the servlet container/RestClient recompute these avoids
    // framing mismatches (e.g. a stale Content-Length after re-serializing
    // the body) that corrupt the HTTP/1.1 response stream.
    private static final Set<String> HOP_BY_HOP_HEADERS = Set.of(
            "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
            "te", "trailer", "transfer-encoding", "upgrade", "content-length", "host");

    public ResponseEntity<byte[]> forward(RestClient restClient, HttpServletRequest request, String forwardPath) {
        byte[] body = readBody(request);
        String query = request.getQueryString();
        String uri = query == null ? forwardPath : forwardPath + "?" + query;

        return restClient.method(HttpMethod.valueOf(request.getMethod()))
                .uri(uri)
                .headers(headers -> copyRequestHeaders(request, headers))
                .body(body)
                .exchange((clientRequest, clientResponse) -> {
                    byte[] responseBody = clientResponse.getBody().readAllBytes();
                    HttpHeaders responseHeaders = new HttpHeaders();
                    clientResponse.getHeaders().forEach((name, values) -> {
                        if (!HOP_BY_HOP_HEADERS.contains(name.toLowerCase())) {
                            responseHeaders.addAll(name, values);
                        }
                    });
                    return ResponseEntity.status(clientResponse.getStatusCode())
                            .headers(responseHeaders)
                            .body(responseBody);
                });
    }

    private byte[] readBody(HttpServletRequest request) {
        try {
            return request.getInputStream().readAllBytes();
        } catch (IOException e) {
            throw new IllegalStateException("failed to read request body", e);
        }
    }

    private void copyRequestHeaders(HttpServletRequest request, HttpHeaders headers) {
        Enumeration<String> names = request.getHeaderNames();
        if (names == null) {
            return;
        }
        while (names.hasMoreElements()) {
            String name = names.nextElement();
            if (HOP_BY_HOP_HEADERS.contains(name.toLowerCase())) {
                continue;
            }
            Enumeration<String> values = request.getHeaders(name);
            while (values.hasMoreElements()) {
                headers.add(name, values.nextElement());
            }
        }
    }
}
