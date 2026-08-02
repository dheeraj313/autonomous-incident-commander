package com.aic.notifications.dto;

import com.aic.notifications.model.Notification;

import java.time.Instant;

public record NotificationResponse(Long id, String username, String source, String eventType, String message,
                                    Instant createdAt) {
    public static NotificationResponse from(Notification notification) {
        return new NotificationResponse(notification.getId(), notification.getUsername(), notification.getSource(),
                notification.getEventType(), notification.getMessage(), notification.getCreatedAt());
    }
}
