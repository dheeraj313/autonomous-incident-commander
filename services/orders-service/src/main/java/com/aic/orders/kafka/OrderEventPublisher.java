package com.aic.orders.kafka;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderEventPublisher {

    private static final String TOPIC = "order-events";

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderEventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(Long orderId, String username, String eventType) {
        String payload = """
                {"orderId":%d,"username":"%s","eventType":"%s","timestamp":"%s"}""".formatted(
                orderId, username, eventType, java.time.Instant.now());
        kafkaTemplate.send(TOPIC, username, payload);
    }
}
