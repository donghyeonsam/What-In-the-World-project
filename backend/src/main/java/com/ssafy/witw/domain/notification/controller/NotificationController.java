package com.ssafy.witw.domain.notification.controller;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.BaseResponse;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.common.response.SuccessCode;
import com.ssafy.witw.domain.notification.dto.response.NotificationListResponse;
import com.ssafy.witw.domain.notification.dto.response.NotificationUnreadCountResponse;
import com.ssafy.witw.domain.notification.service.NotificationService;
import com.ssafy.witw.domain.notification.dto.request.NotificationSettingRequest;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/v1/notifications")
@Tag(name = "알림", description = "알림 조회 및 관리 API")
public class NotificationController {

    private final NotificationService notificationService;

    @GetMapping
    @Operation(summary = "내 알림 목록 조회")
    public ResponseEntity<BaseResponse<NotificationListResponse>> getNotifications(
            HttpServletRequest request,
            @RequestParam(defaultValue = "1") int page,
            @RequestParam(defaultValue = "20") int size
    ) {

        HttpSession session = request.getSession(false);

        if (session == null) throw new GlobalException(ErrorCode.UNAUTHORIZED);


        Object attribute = session.getAttribute("userId");

        if (!(attribute instanceof Long userId)) throw new GlobalException(ErrorCode.UNAUTHORIZED);


        NotificationListResponse response = notificationService.getNotifications(userId, page, size);

        return BaseResponse.success(SuccessCode.REQUEST_SUCCESS, response);
    }

    @PatchMapping("/{notificationId}/read")
    @Operation(summary = "개별 알림 읽음 처리")
    public ResponseEntity<BaseResponse<Void>> markAsRead(
            @PathVariable Long notificationId, HttpServletRequest request
    ) {
        HttpSession session = request.getSession(false);

        if (session == null) throw new GlobalException(ErrorCode.UNAUTHORIZED);


        Object attribute = session.getAttribute("userId");

        if (!(attribute instanceof Long userId)) throw new GlobalException(ErrorCode.UNAUTHORIZED);

        notificationService.markAsRead(userId, notificationId);

        return BaseResponse.success(SuccessCode.REQUEST_SUCCESS);
    }

    @PatchMapping("/read-all")
    @Operation(summary = "알림 전체 읽음 처리")
    public ResponseEntity<BaseResponse<Void>> markAllAsRead(HttpServletRequest request) {
        HttpSession session = request.getSession(false);

        if (session == null) throw new GlobalException(ErrorCode.UNAUTHORIZED);


        Object attribute = session.getAttribute("userId");

        if (!(attribute instanceof Long userId)) throw new GlobalException(ErrorCode.UNAUTHORIZED);


        notificationService.markAllAsRead(userId);

        return BaseResponse.success(SuccessCode.REQUEST_SUCCESS);
    }

    @DeleteMapping("/{notificationId}")
    @Operation(summary = "개별 알림 삭제")
    public ResponseEntity<BaseResponse<Void>> deleteNotification(
            @PathVariable Long notificationId, HttpServletRequest request
    ) {
        HttpSession session = request.getSession(false);

        if (session == null) throw new GlobalException(ErrorCode.UNAUTHORIZED);

        Object attribute = session.getAttribute("userId");

        if (!(attribute instanceof Long userId)) throw new GlobalException(ErrorCode.UNAUTHORIZED);

        notificationService.deleteNotification(userId, notificationId);

        return BaseResponse.success(SuccessCode.REQUEST_SUCCESS);
    }

    @GetMapping("/unread-count")
    @Operation(summary = "미읽음 알림 개수 조회")
    public ResponseEntity<BaseResponse<NotificationUnreadCountResponse>> getUnreadCount(
            HttpServletRequest request
    ) {
        HttpSession session = request.getSession(false);

        if (session == null) throw new GlobalException(ErrorCode.UNAUTHORIZED);


        Object attribute = session.getAttribute("userId");

        if (!(attribute instanceof Long userId)) throw new GlobalException(ErrorCode.UNAUTHORIZED);


        NotificationUnreadCountResponse response = notificationService.getUnreadCount(userId);

        return BaseResponse.success(SuccessCode.REQUEST_SUCCESS, response);
    }

    @PatchMapping("/settings")
    @Operation(summary = "관심사 알림 전체 설정")
    public ResponseEntity<BaseResponse<Void>> updateNotificationSetting(
            @Valid @RequestBody NotificationSettingRequest body,
            HttpServletRequest request
    ) {
        HttpSession session = request.getSession(false);

        if (session == null) throw new GlobalException(ErrorCode.UNAUTHORIZED);

        Object attribute = session.getAttribute("userId");

        if (!(attribute instanceof Long userId)) throw new GlobalException(ErrorCode.UNAUTHORIZED);

        notificationService.updateNotificationSetting(userId, body.enabled());

        return BaseResponse.success(SuccessCode.REQUEST_SUCCESS);
    }
}