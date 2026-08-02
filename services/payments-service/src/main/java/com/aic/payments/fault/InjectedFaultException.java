package com.aic.payments.fault;

public class InjectedFaultException extends RuntimeException {
    public InjectedFaultException(String message) {
        super(message);
    }
}
