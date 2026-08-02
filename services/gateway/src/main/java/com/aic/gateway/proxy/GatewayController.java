package com.aic.gateway.proxy;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class GatewayController {

    private final RestClient authServiceRestClient;
    private final RestClient ordersServiceRestClient;
    private final ProxyService proxyService;

    public GatewayController(RestClient authServiceRestClient, RestClient ordersServiceRestClient,
                              ProxyService proxyService) {
        this.authServiceRestClient = authServiceRestClient;
        this.ordersServiceRestClient = ordersServiceRestClient;
        this.proxyService = proxyService;
    }

    @RequestMapping("/api/auth/**")
    public ResponseEntity<byte[]> proxyAuth(HttpServletRequest request) {
        return proxyService.forward(authServiceRestClient, request, request.getRequestURI());
    }

    @RequestMapping("/api/orders/**")
    public ResponseEntity<byte[]> proxyOrders(HttpServletRequest request) {
        return proxyService.forward(ordersServiceRestClient, request, request.getRequestURI());
    }
}
