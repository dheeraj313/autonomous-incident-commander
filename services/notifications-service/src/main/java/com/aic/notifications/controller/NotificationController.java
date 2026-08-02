package com.aic.notifications.controller;

import com.aic.notifications.dto.NotificationResponse;
import com.aic.notifications.repository.NotificationRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/notifications")
public class NotificationController {

    private final NotificationRepository notificationRepository;

    public NotificationController(NotificationRepository notificationRepository) {
        this.notificationRepository = notificationRepository;
    }

    @GetMapping
    public List<NotificationResponse> forUser(@RequestParam String username) {
        return notificationRepository.findByUsernameOrderByCreatedAtDesc(username).stream()
                .map(NotificationResponse::from)
                .toList();
    }
}
