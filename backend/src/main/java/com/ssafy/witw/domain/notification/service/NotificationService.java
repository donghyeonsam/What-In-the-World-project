package com.ssafy.witw.domain.notification.service;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.domain.interest.dao.UserInterestThemeRepository;
import com.ssafy.witw.domain.notification.dao.NotificationRepository;
import com.ssafy.witw.domain.notification.dao.NotificationSettingRepository;
import com.ssafy.witw.domain.notification.dto.response.NotificationListResponse;
import com.ssafy.witw.domain.notification.dto.response.NotificationResponse;
import com.ssafy.witw.domain.notification.dto.response.NotificationSettingResponse;
import com.ssafy.witw.domain.notification.dto.response.NotificationUnreadCountResponse;
import com.ssafy.witw.domain.notification.entity.Notification;
import com.ssafy.witw.domain.notification.entity.NotificationSetting;
import com.ssafy.witw.domain.user.dao.UserRepository;
import com.ssafy.witw.domain.user.entity.User;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.ZoneId;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class NotificationService {

    private final NotificationRepository notificationRepository;
    private final UserRepository userRepository;
    private final NotificationSettingRepository notificationSettingRepository;
    private final UserInterestThemeRepository userInterestThemeRepository;

    public NotificationListResponse getNotifications(Long userId, int page, int size) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new GlobalException(ErrorCode.UNAUTHORIZED));

        if (user.isWithdrawn()) throw new GlobalException(ErrorCode.UNAUTHORIZED);


        if (page < 1 || size < 1 || size > 100) throw new GlobalException(ErrorCode.INVALID_INPUT_VALUE);


        PageRequest pageable = PageRequest.of(
                page - 1,
                size,
                Sort.by(
                        Sort.Order.desc("createdAt"),
                        Sort.Order.desc("id")
                )
        );

        Slice<Notification> result = notificationRepository.findByUserIdAndDeletedAtIsNull(userId, pageable);

        return new NotificationListResponse(
                result.getContent().stream()
                        .map(NotificationResponse::from)
                        .toList(),
                page,
                size,
                result.hasNext()
        );
    }

    @Transactional
    public void markAsRead(Long userId, Long notificationId) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new GlobalException(ErrorCode.UNAUTHORIZED));

        if (user.isWithdrawn()) {
            throw new GlobalException(ErrorCode.UNAUTHORIZED);
        }

        int updated = notificationRepository.markAsRead(
                notificationId,
                userId,
                LocalDateTime.now(ZoneId.of("Asia/Seoul"))
        );

        if (updated == 0) {
            throw new GlobalException(ErrorCode.ENTITY_NOT_FOUND);
        }
    }

    @Transactional
    public void markAllAsRead(Long userId) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new GlobalException(ErrorCode.UNAUTHORIZED));

        if (user.isWithdrawn()) throw new GlobalException(ErrorCode.UNAUTHORIZED);


        notificationRepository.markAllAsRead(
                userId,
                LocalDateTime.now(ZoneId.of("Asia/Seoul"))
        );
    }

    @Transactional
    public void deleteNotification(Long userId, Long notificationId) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new GlobalException(ErrorCode.UNAUTHORIZED));

        if (user.isWithdrawn()) throw new GlobalException(ErrorCode.UNAUTHORIZED);


        int updated = notificationRepository.softDelete(
                notificationId,
                userId,
                LocalDateTime.now(ZoneId.of("Asia/Seoul"))
        );

        if (updated == 0) throw new GlobalException(ErrorCode.ENTITY_NOT_FOUND);

    }

    public NotificationUnreadCountResponse getUnreadCount(Long userId) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new GlobalException(ErrorCode.UNAUTHORIZED));

        if (user.isWithdrawn()) throw new GlobalException(ErrorCode.UNAUTHORIZED);

        long unreadCount = notificationRepository.countByUserIdAndReadAtIsNullAndDeletedAtIsNull(userId);

        return new NotificationUnreadCountResponse(unreadCount);
    }

    @Transactional
    public void updateNotificationSetting(Long userId, boolean enabled) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new GlobalException(ErrorCode.UNAUTHORIZED));

        if (user.isWithdrawn()) {
            throw new GlobalException(ErrorCode.UNAUTHORIZED);
        }

        notificationSettingRepository.upsertSetting(userId, enabled);
    }

    public NotificationSettingResponse getNotificationSetting(Long userId) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new GlobalException(ErrorCode.UNAUTHORIZED));

        if (user.isWithdrawn()) throw new GlobalException(ErrorCode.UNAUTHORIZED);


        boolean enabled = notificationSettingRepository.findById(userId)
                .map(NotificationSetting::isEnabled)
                .orElse(true);

        return new NotificationSettingResponse(enabled);
    }

    @Transactional
    public void updateThemeNotificationSetting(
            Long userId,
            Long themeId,
            boolean enabled
    ) {
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new GlobalException(ErrorCode.UNAUTHORIZED));

        if (user.isWithdrawn()) throw new GlobalException(ErrorCode.UNAUTHORIZED);


        int updated = userInterestThemeRepository.updateNotificationEnabled(
                userId,
                themeId,
                enabled
        );

        if (updated == 0) throw new GlobalException(ErrorCode.ENTITY_NOT_FOUND);

    }
}