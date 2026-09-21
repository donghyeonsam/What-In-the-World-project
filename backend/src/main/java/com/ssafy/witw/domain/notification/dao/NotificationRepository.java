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
import java.util.List;

public interface NotificationRepository extends JpaRepository<Notification, Long> {

    @EntityGraph(attributePaths = {"theme", "theme.field"})
    Slice<Notification> findByUserIdAndReadAtIsNullAndDeletedAtIsNull(Long userId, Pageable pageable);

    long countByUserIdAndReadAtIsNullAndDeletedAtIsNull(Long userId);

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("""
        UPDATE Notification n
        SET n.readAt = COALESCE(n.readAt, :readAt),
            n.deletedAt = :readAt
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
        SET n.readAt = :readAt,
            n.deletedAt = :readAt
        WHERE n.userId = :userId
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

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query(value = """
    INSERT INTO notification (
        user_id,
        theme_id,
        title,
        message,
        article_count,
        period_start,
        period_end
    )
    SELECT
        i.user_id,
        t.id,
        '[' || t.name || ']에 새로운 기사가 올라왔습니다.',
        '새로운 기사 ' || COUNT(*) || '건을 확인해보세요.',
        CAST(COUNT(*) AS INTEGER),
        :periodStart,
        :periodEnd
    FROM user_interest_theme i
    JOIN users u
      ON u.id = i.user_id
    JOIN theme t
      ON t.id = i.theme_id
    JOIN article a
      ON a.theme_id = i.theme_id
    LEFT JOIN notification_setting s
      ON s.user_id = i.user_id
    WHERE u.withdrawn_at IS NULL
      AND i.notification_enabled = TRUE
      AND COALESCE(s.enabled, TRUE) = TRUE
      AND a.deleted_at IS NULL
      AND a.created_at >= :periodStart
      AND a.created_at < :periodEnd
      AND a.created_at >= i.created_at
    GROUP BY i.user_id, t.id, t.name
    ON CONFLICT (user_id, theme_id, period_start, period_end)
    DO NOTHING
    """, nativeQuery = true)

    int createThemeNotifications(
            @Param("periodStart") LocalDateTime periodStart,
            @Param("periodEnd") LocalDateTime periodEnd
    );

    @Query("""
    SELECT DISTINCT n.userId
    FROM Notification n
    WHERE n.periodStart = :periodStart
      AND n.periodEnd = :periodEnd
      AND n.deletedAt IS NULL
    """)
    List<Long> findRecipientIdsByPeriod(
            @Param("periodStart") LocalDateTime periodStart,
            @Param("periodEnd") LocalDateTime periodEnd
    );

}
