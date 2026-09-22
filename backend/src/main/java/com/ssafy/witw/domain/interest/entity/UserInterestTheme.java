package com.ssafy.witw.domain.interest.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Getter
@Entity
@Table(name = "user_interest_theme")
@IdClass(UserInterestThemeId.class)
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class UserInterestTheme {

    @Id
    @Column(name = "user_id", nullable = false)
    private Long userId;

    @Id
    @Column(name = "theme_id", nullable = false)
    private Long themeId;

    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;

    @Column(name = "notification_enabled", nullable = false)
    private boolean notificationEnabled = true;

    public static UserInterestTheme create(Long userId, Long themeId) {
        UserInterestTheme interest = new UserInterestTheme();

        interest.userId = userId;
        interest.themeId = themeId;
        interest.createdAt = LocalDateTime.now();

        return interest;
    }
}

