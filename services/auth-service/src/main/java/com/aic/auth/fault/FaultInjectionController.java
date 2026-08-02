package com.aic.auth.fault;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * Admin-only endpoints used by the chaos scripts / remediation engine to
 * inject or clear synthetic faults in this service without redeploying it.
 */
@RestController
@RequestMapping("/admin/fault-injection")
public class FaultInjectionController {

    private final FaultInjectionService faultInjectionService;

    public FaultInjectionController(FaultInjectionService faultInjectionService) {
        this.faultInjectionService = faultInjectionService;
    }

    public record FaultInjectionRequest(
            @Min(0) @Max(60000) Integer latencyMs,
            @Min(0) @Max(1) Double errorRate) {
    }

    @PostMapping
    public Map<String, Object> setFault(@RequestBody FaultInjectionRequest request) {
        if (request.latencyMs() != null) {
            faultInjectionService.setLatencyMs(request.latencyMs());
        }
        if (request.errorRate() != null) {
            faultInjectionService.setErrorRate(request.errorRate());
        }
        return status();
    }

    @DeleteMapping
    public Map<String, Object> clearFault() {
        faultInjectionService.clear();
        return status();
    }

    @GetMapping
    public Map<String, Object> status() {
        return Map.of(
                "latencyMs", faultInjectionService.getLatencyMs(),
                "errorRate", faultInjectionService.getErrorRate());
    }
}
