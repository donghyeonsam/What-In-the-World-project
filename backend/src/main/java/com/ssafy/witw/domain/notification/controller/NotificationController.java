package com.ssafy.witw.domain.notification.controller;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.BaseResponse;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.common.response.SuccessCode;
import com.ssafy.witw.domain.notification.dto.response.NotificationListResponse;
import com.ssafy.witw.domain.notification.service.NotificationService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

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
}