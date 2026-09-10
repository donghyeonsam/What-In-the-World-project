package com.ssafy.witw.domain.auth.controller;

import com.ssafy.witw.common.response.BaseResponse;
import com.ssafy.witw.common.response.SuccessCode;
import com.ssafy.witw.domain.auth.dto.EmailExistsResponse;
import com.ssafy.witw.domain.auth.service.AuthService;
import com.ssafy.witw.domain.auth.dto.SignupRequest;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;


@RestController
@RequiredArgsConstructor
@RequestMapping("/api/v1/auth")
@Tag(name = "인증", description = "회원가입 및 로그인 API")
public class AuthController {
    private final AuthService authService;

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


}
