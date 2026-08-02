package com.aic.inventory.fault;

public class InjectedFaultException extends RuntimeException {
    public InjectedFaultException(String message) {
        super(message);
    }
}
