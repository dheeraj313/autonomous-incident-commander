package com.aic.inventory.kafka;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class InventoryEventPublisher {

    private static final String TOPIC = "inventory-events";

    private final KafkaTemplate<String, String> kafkaTemplate;

    public InventoryEventPublisher(KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(String item, int quantity, String eventType) {
        String payload = """
                {"item":"%s","quantity":%d,"eventType":"%s","timestamp":"%s"}""".formatted(
                item, quantity, eventType, java.time.Instant.now());
        kafkaTemplate.send(TOPIC, item, payload);
    }
}
