package com.aic.payments.kafka;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class PaymentEventPublisher {

    private static final String TOPIC = "payment-events";

    private final KafkaTemplate<String, String> kafkaTemplate;

    public PaymentEventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(Long orderId, String username, String eventType) {
        String payload = """
                {"orderId":%d,"username":"%s","eventType":"%s","timestamp":"%s"}""".formatted(
                orderId, username, eventType, java.time.Instant.now());
        kafkaTemplate.send(TOPIC, username, payload);
    }
}
