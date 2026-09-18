package com.ssafy.witw.domain.notification.dao;

import com.ssafy.witw.domain.notification.entity.Notification;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.LocalDateTime;

public interface NotificationRepository extends JpaRepository<Notification, Long> {

    @EntityGraph(attributePaths = {"theme", "theme.field"})
    Slice<Notification> findByUserIdAndDeletedAtIsNull(
            Long userId,
            Pageable pageable
    );

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("""
        UPDATE Notification n
        SET n.readAt = COALESCE(n.readAt, :readAt)
        WHERE n.id = :notificationId
          AND n.userId = :userId
          AND n.deletedAt IS NULL
    """)
    int markAsRead(
            @Param("notificationId") Long notificationId,
            @Param("userId") Long userId,
            @Param("readAt") LocalDateTime readAt
    );

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("""
        UPDATE Notification n
        SET n.readAt = :readAt
        WHERE n.userId = :userId
          AND n.readAt IS NULL
          AND n.deletedAt IS NULL
    """)
    int markAllAsRead(
            @Param("userId") Long userId,
            @Param("readAt") LocalDateTime readAt
    );

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("""
        UPDATE Notification n
        SET n.deletedAt = :deletedAt
        WHERE n.id = :notificationId
          AND n.userId = :userId
          AND n.deletedAt IS NULL
    """)
    int softDelete(
            @Param("notificationId") Long notificationId,
            @Param("userId") Long userId,
            @Param("deletedAt") LocalDateTime deletedAt
    );
}