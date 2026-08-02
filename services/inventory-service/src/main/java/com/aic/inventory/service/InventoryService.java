package com.aic.inventory.service;

import com.aic.inventory.dto.InventoryResponse;
import com.aic.inventory.kafka.InventoryEventPublisher;
import com.aic.inventory.model.InventoryItem;
import com.aic.inventory.repository.InventoryItemRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class InventoryService {

    private final InventoryItemRepository repository;
    private final InventoryEventPublisher eventPublisher;
    private final int defaultStock;

    public InventoryService(InventoryItemRepository repository, InventoryEventPublisher eventPublisher,
                             @Value("${aic.inventory.default-stock}") int defaultStock) {
        this.repository = repository;
        this.eventPublisher = eventPublisher;
        this.defaultStock = defaultStock;
    }

    /**
     * Reserves stock for an item, auto-provisioning a catalog entry with
     * {@code defaultStock} units the first time an unknown SKU is seen. This
     * keeps the demo self-contained (no separate catalog-seeding step) while
     * still exercising real reserve/insufficient-stock logic.
     */
    @Transactional
    public InventoryResponse reserve(String item, int quantity) {
        InventoryItem inventoryItem = repository.findForUpdateBySku(item)
                .orElseGet(() -> repository.save(new InventoryItem(item, defaultStock)));

        if (inventoryItem.getQuantityAvailable() < quantity) {
            eventPublisher.publish(item, quantity, "INVENTORY_INSUFFICIENT");
            throw new ResponseStatusException(HttpStatus.CONFLICT,
                    "insufficient stock for " + item + ": available=" + inventoryItem.getQuantityAvailable());
        }

        inventoryItem.setQuantityAvailable(inventoryItem.getQuantityAvailable() - quantity);
        repository.save(inventoryItem);
        eventPublisher.publish(item, quantity, "INVENTORY_RESERVED");
        return new InventoryResponse(inventoryItem.getSku(), inventoryItem.getQuantityAvailable());
    }

    @Transactional
    public InventoryResponse getStock(String item) {
        InventoryItem inventoryItem = repository.findBySku(item)
                .orElseGet(() -> repository.save(new InventoryItem(item, defaultStock)));
        return new InventoryResponse(inventoryItem.getSku(), inventoryItem.getQuantityAvailable());
    }
}
