package com.aic.inventory.repository;

import com.aic.inventory.model.InventoryItem;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;

import jakarta.persistence.LockModeType;
import java.util.Optional;

public interface InventoryItemRepository extends JpaRepository<InventoryItem, Long> {

    Optional<InventoryItem> findBySku(String sku);

    // Only used inside an active @Transactional method (reserve()); a
    // pessimistic lock query requires a transaction context to acquire the
    // row lock, so it must never be called from a non-transactional method.
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    Optional<InventoryItem> findForUpdateBySku(String sku);
}
