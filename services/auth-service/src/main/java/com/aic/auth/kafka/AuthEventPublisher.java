package com.aic.auth.kafka;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class AuthEventPublisher {

    private static final String TOPIC = "auth-events";

    private final KafkaTemplate<String, String> kafkaTemplate;

    public AuthEventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String username, String eventType) {
        String payload = """
                {"username":"%s","eventType":"%s","timestamp":"%s"}""".formatted(
                username, eventType, java.time.Instant.now());
        kafkaTemplate.send(TOPIC, username, payload);
    }
}
