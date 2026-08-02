package com.aic.notifications.kafka;

import com.aic.notifications.fault.FaultInjectionService;
import com.aic.notifications.fault.InjectedFaultException;
import com.aic.notifications.model.Notification;
import com.aic.notifications.repository.NotificationRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class NotificationEventListener {

    private static final Logger log = LoggerFactory.getLogger(NotificationEventListener.class);

    private final NotificationRepository notificationRepository;
    private final FaultInjectionService faultInjectionService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public NotificationEventListener(NotificationRepository notificationRepository,
                                      FaultInjectionService faultInjectionService) {
        this.notificationRepository = notificationRepository;
        this.faultInjectionService = faultInjectionService;
    }

    @KafkaListener(topics = "auth-events", groupId = "notifications-service")
    public void onAuthEvent(String payload) {
        handle("auth-service", payload, "username");
    }

    @KafkaListener(topics = "order-events", groupId = "notifications-service")
    public void onOrderEvent(String payload) {
        handle("orders-service", payload, "username");
    }

    @KafkaListener(topics = "payment-events", groupId = "notifications-service")
    public void onPaymentEvent(String payload) {
        handle("payments-service", payload, "username");
    }

    private void handle(String source, String payload, String usernameField) {
        try {
            // Fault injection here simulates a notification consumer falling
            // behind or dropping messages during an incident (visible as
            // consumer lag / missing notifications in the demo).
            faultInjectionService.apply();

            JsonNode node = objectMapper.readTree(payload);
            String username = node.path(usernameField).asText("unknown");
            String eventType = node.path("eventType").asText("UNKNOWN");
            String message = source + " event: " + eventType;

            notificationRepository.save(new Notification(username, source, eventType, message));
        } catch (InjectedFaultException e) {
            log.warn("Dropped notification from {} due to injected fault: {}", source, e.getMessage());
        } catch (Exception e) {
            log.error("Failed to process notification event from {}: {}", source, payload, e);
        }
    }
}
