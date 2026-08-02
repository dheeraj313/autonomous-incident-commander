package com.aic.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.client.RestClient;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OrdersServiceApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersServiceApplication.class, args);
    }

    @Bean
    public RestClient authServiceRestClient(@Value("${aic.auth-service.url}") String authServiceUrl) {
        return RestClient.builder().baseUrl(authServiceUrl).build();
    }

    @Bean
    public RestClient inventoryServiceRestClient(@Value("${aic.inventory-service.url}") String inventoryServiceUrl) {
        return RestClient.builder().baseUrl(inventoryServiceUrl).build();
    }

    @Bean
    public RestClient paymentsServiceRestClient(@Value("${aic.payments-service.url}") String paymentsServiceUrl) {
        return RestClient.builder().baseUrl(paymentsServiceUrl).build();
    }
}
