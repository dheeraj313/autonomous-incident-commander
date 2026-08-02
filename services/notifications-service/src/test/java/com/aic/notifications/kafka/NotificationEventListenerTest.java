package com.aic.notifications.kafka;

import com.aic.notifications.fault.FaultInjectionService;
import com.aic.notifications.fault.InjectedFaultException;
import com.aic.notifications.model.Notification;
import com.aic.notifications.repository.NotificationRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

class NotificationEventListenerTest {

    private NotificationRepository notificationRepository;
    private FaultInjectionService faultInjectionService;
    private NotificationEventListener listener;

    @BeforeEach
    void setUp() {
        notificationRepository = mock(NotificationRepository.class);
        faultInjectionService = mock(FaultInjectionService.class);
        listener = new NotificationEventListener(notificationRepository, faultInjectionService);
    }

    @Test
    void authEventIsParsedAndSavedAsNotification() {
        listener.onAuthEvent("{\"username\":\"alice\",\"eventType\":\"USER_REGISTERED\"}");

        verify(notificationRepository).save(argThat((Notification n) ->
                n.getUsername().equals("alice")
                        && n.getSource().equals("auth-service")
                        && n.getEventType().equals("USER_REGISTERED")
                        && n.getMessage().contains("USER_REGISTERED")));
    }

    @Test
    void orderEventIsParsedAndSavedWithOrdersServiceAsSource() {
        listener.onOrderEvent("{\"username\":\"bob\",\"eventType\":\"ORDER_COMPLETED\"}");

        verify(notificationRepository).save(argThat((Notification n) ->
                n.getUsername().equals("bob") && n.getSource().equals("orders-service")));
    }

    @Test
    void paymentEventIsParsedAndSavedWithPaymentsServiceAsSource() {
        listener.onPaymentEvent("{\"username\":\"carol\",\"eventType\":\"PAYMENT_CHARGED\"}");

        verify(notificationRepository).save(argThat((Notification n) ->
                n.getUsername().equals("carol") && n.getSource().equals("payments-service")));
    }

    @Test
    void missingUsernameFieldFallsBackToUnknown() {
        listener.onAuthEvent("{\"eventType\":\"USER_LOGIN\"}");

        verify(notificationRepository).save(argThat((Notification n) -> n.getUsername().equals("unknown")));
    }

    @Test
    void injectedFaultDropsTheMessageInsteadOfSavingIt() {
        doThrow(new InjectedFaultException("simulated drop")).when(faultInjectionService).apply();

        listener.onAuthEvent("{\"username\":\"alice\",\"eventType\":\"USER_LOGIN\"}");

        verify(notificationRepository, never()).save(any());
    }

    @Test
    void malformedJsonPayloadIsCaughtAndDoesNotSaveOrThrow() {
        listener.onAuthEvent("not-json-at-all");

        verify(notificationRepository, never()).save(any());
    }
}
