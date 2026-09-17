package com.ssafy.witw.domain.user.controller;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.BaseResponse;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.common.response.SuccessCode;
import com.ssafy.witw.domain.user.dto.request.WithdrawRequest;
import com.ssafy.witw.domain.user.dto.response.UserResponse;
import com.ssafy.witw.domain.user.service.UserService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/v1/users")
@Tag(name = "회원", description = "회원 관리 API")
public class UserController {
    private final UserService userService;

    @PatchMapping("/withdraw")
    @Operation(summary = "회원 탈퇴")
    public ResponseEntity<BaseResponse<Void>> withdraw(
            @Valid @RequestBody WithdrawRequest request, HttpServletRequest httpRequest
    ){
        HttpSession session = httpRequest.getSession(false);

        if(session == null) throw new GlobalException(ErrorCode.UNAUTHORIZED);

        Object attribute = session.getAttribute("userId");

        if(!(attribute instanceof Long userId)) throw new GlobalException(ErrorCode.UNAUTHORIZED);

        userService.withdraw(userId, request);

        session.invalidate();

        return BaseResponse.success(SuccessCode.WITHDRAW_SUCCESS);
    }

    @GetMapping("/me")
    @Operation(summary = "로그인 사용자 정보 조회")
    public ResponseEntity<BaseResponse<UserResponse>> getCurrentUser(
            HttpServletRequest httpRequest
    ){
        HttpSession session = httpRequest.getSession(false);

        if(session == null) throw new GlobalException(ErrorCode.UNAUTHORIZED);

        Object attribute = session.getAttribute("userId");

        if(!(attribute instanceof Long userId)) throw new GlobalException(ErrorCode.UNAUTHORIZED);

        UserResponse response = userService.getCurrentUser(userId);

        return BaseResponse.success(SuccessCode.REQUEST_SUCCESS, response);
    }

}
