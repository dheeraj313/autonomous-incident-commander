package com.aic.inventory.controller;

import com.aic.inventory.dto.InventoryResponse;
import com.aic.inventory.dto.ReserveRequest;
import com.aic.inventory.fault.FaultInjectionService;
import com.aic.inventory.service.InventoryService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/inventory")
public class InventoryController {

    private final InventoryService inventoryService;
    private final FaultInjectionService faultInjectionService;

    public InventoryController(InventoryService inventoryService, FaultInjectionService faultInjectionService) {
        this.inventoryService = inventoryService;
        this.faultInjectionService = faultInjectionService;
    }

    @PostMapping("/reserve")
    public InventoryResponse reserve(@Valid @RequestBody ReserveRequest request) {
        faultInjectionService.apply();
        return inventoryService.reserve(request.item(), request.quantity());
    }

    @GetMapping("/{item}")
    public InventoryResponse getStock(@PathVariable String item) {
        faultInjectionService.apply();
        return inventoryService.getStock(item);
    }
}
