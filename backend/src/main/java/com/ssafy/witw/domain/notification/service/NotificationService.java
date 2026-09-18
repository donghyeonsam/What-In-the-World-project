package com.ssafy.witw.domain.notification.service;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.domain.notification.dao.NotificationRepository;
import com.ssafy.witw.domain.notification.dto.response.NotificationListResponse;
import com.ssafy.witw.domain.notification.dto.response.NotificationResponse;
import com.ssafy.witw.domain.notification.entity.Notification;
import com.ssafy.witw.domain.user.dao.UserRepository;
import com.ssafy.witw.domain.user.entity.User;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class NotificationService {

    private final NotificationRepository notificationRepository;
    private final UserRepository userRepository;

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
}