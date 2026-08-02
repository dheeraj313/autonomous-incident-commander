package com.aic.inventory.fault;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Map;

@RestControllerAdvice
public class FaultInjectionExceptionHandler {

    @ExceptionHandler(InjectedFaultException.class)
    public ResponseEntity<Map<String, String>> handle(InjectedFaultException ex) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of("error", ex.getMessage()));
    }
}
