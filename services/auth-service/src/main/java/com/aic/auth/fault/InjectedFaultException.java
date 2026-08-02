package com.aic.auth.fault;

public class InjectedFaultException extends RuntimeException {
    public InjectedFaultException(String message) {
        super(message);
    }
}
