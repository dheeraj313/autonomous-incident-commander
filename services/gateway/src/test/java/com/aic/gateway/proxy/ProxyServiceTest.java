package com.aic.gateway.proxy;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

/**
 * Covers ProxyService's hop-by-hop header handling: this is exactly the kind
 * of logic (see docs/architecture.md "Deployment notes") that previously
 * corrupted HTTP/1.1 framing when blindly forwarded between hops.
 */
class ProxyServiceTest {

    private final ProxyService proxyService = new ProxyService();

    @Test
    void stripsHopByHopRequestHeadersButForwardsOthers() {
        RestClient.Builder builder = RestClient.builder().baseUrl("http://downstream-service");
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        RestClient restClient = builder.build();

        server.expect(requestTo("http://downstream-service/api/orders/123"))
                .andExpect(request -> {
                    HttpHeaders headers = request.getHeaders();
                    assertThat(headers.get("Authorization")).containsExactly("Bearer demo-token");
                    assertThat(headers.containsKey("Connection")).isFalse();
                    assertThat(headers.containsKey("Host")).isFalse();
                    // Content-Length may be recomputed by RestClient itself for the (empty) body;
                    // what matters is that the original, stale client-supplied value isn't forwarded.
                    assertThat(headers.getFirst("Content-Length")).isNotEqualTo("9999");
                })
                .andRespond(withSuccess("{\"ok\":true}", MediaType.APPLICATION_JSON));

        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/orders/123");
        request.addHeader("Authorization", "Bearer demo-token");
        request.addHeader("Connection", "keep-alive");
        request.addHeader("Content-Length", "9999");
        request.addHeader("Host", "gateway:8080");

        ResponseEntity<byte[]> response = proxyService.forward(restClient, request, "/api/orders/123");

        server.verify();
        assertThat(response.getStatusCode().value()).isEqualTo(200);
        assertThat(new String(response.getBody())).isEqualTo("{\"ok\":true}");
    }

    @Test
    void stripsHopByHopResponseHeadersButKeepsOthers() {
        RestClient.Builder builder = RestClient.builder().baseUrl("http://downstream-service");
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        RestClient restClient = builder.build();

        HttpHeaders responseHeaders = new HttpHeaders();
        responseHeaders.add("X-Custom-Response", "keep-me");
        responseHeaders.add("Transfer-Encoding", "chunked");
        responseHeaders.add("Connection", "close");

        server.expect(requestTo("http://downstream-service/api/orders/123"))
                .andRespond(withSuccess("{\"ok\":true}", MediaType.APPLICATION_JSON).headers(responseHeaders));

        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/orders/123");

        ResponseEntity<byte[]> response = proxyService.forward(restClient, request, "/api/orders/123");

        server.verify();
        assertThat(response.getHeaders().get("X-Custom-Response")).containsExactly("keep-me");
        assertThat(response.getHeaders().containsKey("Transfer-Encoding")).isFalse();
        assertThat(response.getHeaders().containsKey("Connection")).isFalse();
    }

    @Test
    void forwardsMethodAndQueryStringToTheDownstreamService() {
        RestClient.Builder builder = RestClient.builder().baseUrl("http://downstream-service");
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        RestClient restClient = builder.build();

        server.expect(requestTo("http://downstream-service/api/orders?status=COMPLETED"))
                .andRespond(withSuccess("[]", MediaType.APPLICATION_JSON));

        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/orders");
        request.setQueryString("status=COMPLETED");

        ResponseEntity<byte[]> response = proxyService.forward(restClient, request, "/api/orders");

        server.verify();
        assertThat(response.getStatusCode().value()).isEqualTo(200);
    }

    @Test
    void passesThroughNonSuccessStatusCodesInsteadOfThrowing() {
        RestClient.Builder builder = RestClient.builder().baseUrl("http://downstream-service");
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        RestClient restClient = builder.build();

        server.expect(requestTo("http://downstream-service/admin/fault-injection"))
                .andRespond(org.springframework.test.web.client.response.MockRestResponseCreators
                        .withStatus(org.springframework.http.HttpStatus.SERVICE_UNAVAILABLE)
                        .body("{\"error\":\"injected fault\"}")
                        .contentType(MediaType.APPLICATION_JSON));

        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/admin/fault-injection");

        ResponseEntity<byte[]> response = proxyService.forward(restClient, request, "/admin/fault-injection");

        server.verify();
        assertThat(response.getStatusCode().value()).isEqualTo(503);
        assertThat(new String(response.getBody())).contains("injected fault");
    }
}
