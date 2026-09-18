package com.ssafy.witw.domain.notification.dao;

import com.ssafy.witw.domain.notification.entity.Notification;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;

public interface NotificationRepository
        extends JpaRepository<Notification, Long> {

    @EntityGraph(attributePaths = {"theme", "theme.field"})
    Slice<Notification> findByUserIdAndDeletedAtIsNull(
            Long userId,
            Pageable pageable
    );
}