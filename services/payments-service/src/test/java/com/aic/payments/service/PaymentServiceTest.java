package com.aic.payments.service;

import com.aic.payments.dto.ChargeRequest;
import com.aic.payments.kafka.PaymentEventPublisher;
import com.aic.payments.model.Payment;
import com.aic.payments.repository.PaymentRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class PaymentServiceTest {

    private PaymentRepository paymentRepository;
    private PaymentEventPublisher eventPublisher;
    private PaymentService paymentService;

    @BeforeEach
    void setUp() {
        paymentRepository = mock(PaymentRepository.class);
        eventPublisher = mock(PaymentEventPublisher.class);
        paymentService = new PaymentService(paymentRepository, eventPublisher);
        when(paymentRepository.save(any(Payment.class))).thenAnswer(invocation -> invocation.getArgument(0));
    }

    @Test
    void chargeAlwaysSucceedsPersistsAndPublishesEvent() {
        ChargeRequest request = new ChargeRequest(1L, "alice", BigDecimal.valueOf(19.99));

        Payment payment = paymentService.charge(request);

        assertThat(payment.getOrderId()).isEqualTo(1L);
        assertThat(payment.getUsername()).isEqualTo("alice");
        assertThat(payment.getAmount()).isEqualByComparingTo(BigDecimal.valueOf(19.99));
        assertThat(payment.getStatus()).isEqualTo("CHARGED");
        verify(paymentRepository).save(any(Payment.class));
        verify(eventPublisher).publish(1L, "alice", "PAYMENT_CHARGED");
    }
}
