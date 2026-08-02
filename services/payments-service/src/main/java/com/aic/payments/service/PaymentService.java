package com.aic.payments.service;

import com.aic.payments.dto.ChargeRequest;
import com.aic.payments.kafka.PaymentEventPublisher;
import com.aic.payments.model.Payment;
import com.aic.payments.repository.PaymentRepository;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    private final PaymentRepository paymentRepository;
    private final PaymentEventPublisher eventPublisher;

    public PaymentService(PaymentRepository paymentRepository, PaymentEventPublisher eventPublisher) {
        this.paymentRepository = paymentRepository;
        this.eventPublisher = eventPublisher;
    }

    /**
     * Always "succeeds" in this sandbox (no real payment provider) unless a
     * fault is injected upstream of this call. Charges are still persisted so
     * the incident/postmortem story has a real audit trail to point to.
     */
    public Payment charge(ChargeRequest request) {
        Payment payment = new Payment(request.orderId(), request.username(), request.amount(), "CHARGED");
        paymentRepository.save(payment);
        eventPublisher.publish(payment.getOrderId(), payment.getUsername(), "PAYMENT_CHARGED");
        return payment;
    }
}
