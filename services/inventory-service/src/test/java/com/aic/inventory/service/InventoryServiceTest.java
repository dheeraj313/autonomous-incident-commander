package com.aic.inventory.service;

import com.aic.inventory.dto.InventoryResponse;
import com.aic.inventory.kafka.InventoryEventPublisher;
import com.aic.inventory.model.InventoryItem;
import com.aic.inventory.repository.InventoryItemRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class InventoryServiceTest {

    private static final int DEFAULT_STOCK = 1000;

    private InventoryItemRepository repository;
    private InventoryEventPublisher eventPublisher;
    private InventoryService inventoryService;

    @BeforeEach
    void setUp() {
        repository = mock(InventoryItemRepository.class);
        eventPublisher = mock(InventoryEventPublisher.class);
        inventoryService = new InventoryService(repository, eventPublisher, DEFAULT_STOCK);
        when(repository.save(any(InventoryItem.class))).thenAnswer(invocation -> invocation.getArgument(0));
    }

    @Test
    void reserveAutoProvisionsUnknownSkuWithDefaultStockThenReserves() {
        when(repository.findForUpdateBySku("widget")).thenReturn(Optional.empty());

        InventoryResponse response = inventoryService.reserve("widget", 10);

        assertThat(response.item()).isEqualTo("widget");
        assertThat(response.quantityAvailable()).isEqualTo(DEFAULT_STOCK - 10);
        verify(eventPublisher).publish("widget", 10, "INVENTORY_RESERVED");
    }

    @Test
    void reserveDecrementsExistingStockWhenSufficient() {
        InventoryItem existing = new InventoryItem("widget", 50);
        when(repository.findForUpdateBySku("widget")).thenReturn(Optional.of(existing));

        InventoryResponse response = inventoryService.reserve("widget", 20);

        assertThat(response.quantityAvailable()).isEqualTo(30);
        assertThat(existing.getQuantityAvailable()).isEqualTo(30);
        verify(eventPublisher).publish("widget", 20, "INVENTORY_RESERVED");
    }

    @Test
    void reserveThrowsConflictAndPublishesInsufficientEventWhenStockTooLow() {
        InventoryItem existing = new InventoryItem("widget", 5);
        when(repository.findForUpdateBySku("widget")).thenReturn(Optional.of(existing));

        assertThatThrownBy(() -> inventoryService.reserve("widget", 10))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("insufficient stock");

        assertThat(existing.getQuantityAvailable()).isEqualTo(5); // unchanged
        verify(eventPublisher).publish("widget", 10, "INVENTORY_INSUFFICIENT");
        verify(eventPublisher, never()).publish(eq("widget"), eq(10), eq("INVENTORY_RESERVED"));
    }

    @Test
    void getStockReturnsExistingItemWithoutModifyingQuantity() {
        InventoryItem existing = new InventoryItem("widget", 42);
        when(repository.findBySku("widget")).thenReturn(Optional.of(existing));

        InventoryResponse response = inventoryService.getStock("widget");

        assertThat(response.quantityAvailable()).isEqualTo(42);
        verify(repository, never()).save(existing);
    }

    @Test
    void getStockAutoProvisionsUnknownSkuWithDefaultStock() {
        when(repository.findBySku("new-sku")).thenReturn(Optional.empty());

        InventoryResponse response = inventoryService.getStock("new-sku");

        assertThat(response.quantityAvailable()).isEqualTo(DEFAULT_STOCK);
    }
}
