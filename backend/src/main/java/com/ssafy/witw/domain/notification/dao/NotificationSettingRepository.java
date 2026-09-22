package com.ssafy.witw.domain.notification.dao;

import com.ssafy.witw.domain.notification.entity.NotificationSetting;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface NotificationSettingRepository
        extends JpaRepository<NotificationSetting, Long> {

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query(value = """
        INSERT INTO notification_setting (user_id, enabled)
        VALUES (:userId, :enabled)
        ON CONFLICT (user_id)
        DO UPDATE SET enabled = EXCLUDED.enabled
       """, nativeQuery = true)
    int upsertSetting(
            @Param("userId") Long userId,
            @Param("enabled") boolean enabled
    );
}