package com.aic.payments.controller;

import com.aic.payments.dto.ChargeRequest;
import com.aic.payments.dto.PaymentResponse;
import com.aic.payments.fault.FaultInjectionService;
import com.aic.payments.model.Payment;
import com.aic.payments.service.PaymentService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/payments")
public class PaymentController {

    private final PaymentService paymentService;
    private final FaultInjectionService faultInjectionService;

    public PaymentController(PaymentService paymentService, FaultInjectionService faultInjectionService) {
        this.paymentService = paymentService;
        this.faultInjectionService = faultInjectionService;
    }

    @PostMapping("/charge")
    public PaymentResponse charge(@Valid @RequestBody ChargeRequest request) {
        faultInjectionService.apply();
        Payment payment = paymentService.charge(request);
        return PaymentResponse.from(payment);
    }
}
