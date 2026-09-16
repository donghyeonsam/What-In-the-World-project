package com.ssafy.witw.domain.auth.controller;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.BaseResponse;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.common.response.SuccessCode;
import com.ssafy.witw.domain.auth.dto.request.*;
import com.ssafy.witw.domain.auth.dto.response.EmailExistsResponse;
import com.ssafy.witw.domain.auth.dto.response.EmailSendResponse;
import com.ssafy.witw.domain.auth.service.AuthService;
import com.ssafy.witw.domain.auth.service.EmailVerificationService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/v1/auth")
@Tag(name = "인증", description = "회원가입 및 로그인 API")
public class AuthController {
    private final AuthService authService;
    private final EmailVerificationService emailVerificationService;

    @PostMapping("/signup")
    @Operation(summary = "이메일 회원가입")
    public ResponseEntity<BaseResponse<Void>> signup(@Valid @RequestBody SignupRequest request){
        authService.signup(request);
        return BaseResponse.success(SuccessCode.SIGNUP_SUCCESS);

    }

    @GetMapping("/exists")
    @Operation(summary = "이메일 중복 확인")
    public ResponseEntity<BaseResponse<EmailExistsResponse>> checkEmailExists(
            @RequestParam
            @NotBlank
            @Email
            @Size(max = 255)
            String email
    ){
        EmailExistsResponse response = authService.checkEmailExists(email);

        return BaseResponse.success(SuccessCode.REQUEST_SUCCESS, response);
    }

    @PostMapping("/email/send")
    @Operation(summary = "회원가입 이메일 인증번호 전송")
    public ResponseEntity<BaseResponse<EmailSendResponse>> sendEmailCode(
            @Valid @RequestBody EmailRequest request
    ){
        EmailSendResponse response = emailVerificationService.sendCode(request);

        return BaseResponse.success(SuccessCode.EMAIL_SEND_SUCCESS, response);
    }

    @PostMapping("/email/verify")
    @Operation(summary = "회원가입 이메일 인증번호 검증")
    public ResponseEntity<BaseResponse<Void>> verifyEmailCode(
            @Valid @RequestBody EmailVerifyRequest request
    ) {
        emailVerificationService.verifyCode(request);

        return BaseResponse.success(SuccessCode.EMAIL_VERIFY_SUCCESS);
    }

    @PostMapping("/login")
    @Operation(summary = "이메일 로그인")
    public ResponseEntity<BaseResponse<Void>> login(
            @Valid @RequestBody LoginRequest loginRequest, HttpServletRequest httpRequest
    ){
        Long userId = authService.login(loginRequest);

        HttpSession preSession = httpRequest.getSession(false);
        if(preSession != null) preSession.invalidate();

        HttpSession session = httpRequest.getSession(true);
        session.setAttribute("userId", userId);

        return BaseResponse.success(SuccessCode.LOGIN_SUCCESS);
    }

    @PostMapping("/logout")
    @Operation(summary = "로그아웃")
    public ResponseEntity<BaseResponse<Void>> logout(
            HttpServletRequest request
    ){
        HttpSession session = request.getSession(false);

        if(session != null) session.invalidate();


        return BaseResponse.success(SuccessCode.LOGOUT_SUCCESS);
    }

    @PostMapping("/password/email/send")
    @Operation(summary = "비밀번호 재설정 인증번호 전송")
    public ResponseEntity<BaseResponse<EmailSendResponse>> sendPasswordResetCode(
            @Valid @RequestBody EmailRequest request
    ){
        EmailSendResponse response = emailVerificationService.sendPasswordResetCode(request);

        return BaseResponse.success(SuccessCode.PASSWORD_RESET_EMAIL_SEND_SUCCESS, response);
    }

    @PostMapping("/password/email/verify")
    @Operation(summary = "비밀번호 재설정 인증번호 검증")
    public ResponseEntity<BaseResponse<Void>> verifyPasswordResetCode(
            @Valid @RequestBody EmailVerifyRequest request, HttpServletRequest httpRequest
    ){
        String verifiedEmail = emailVerificationService.verifyPasswordResetCode(request);

        HttpSession session = httpRequest.getSession(true);

        session.setAttribute("passwordResetEmail", verifiedEmail);

        return BaseResponse.success(SuccessCode.PASSWORD_RESET_EMAIL_VERIFY_SUCCESS);
    }

    @PostMapping("/password/reset")
    @Operation(summary = "비밀번호 재설정")
    public ResponseEntity<BaseResponse<Void>> resetPassword(
            @Valid @RequestBody PasswordResetRequest request, HttpServletRequest httpRequest
    ){
        HttpSession session = httpRequest.getSession(false);

        if(session == null) throw new GlobalException(ErrorCode.PASSWORD_RESET_NOT_VERIFIED);

        Object emailAttribute = session.getAttribute("passwordResetEmail");

        if(!(emailAttribute instanceof String email)) throw new GlobalException(ErrorCode.PASSWORD_RESET_NOT_VERIFIED);

        authService.resetPassword(email, request.newPassword());

        session.invalidate();

        return BaseResponse.success(SuccessCode.PASSWORD_RESET_SUCCESS);
    }

}
