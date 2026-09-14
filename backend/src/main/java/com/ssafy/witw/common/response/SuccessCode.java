package com.ssafy.witw.common.response;

import lombok.AccessLevel;
import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;

@Getter
@RequiredArgsConstructor(access = AccessLevel.PRIVATE)
public enum SuccessCode {

    // COMMON
    REQUEST_SUCCESS(HttpStatus.OK, "요청이 성공적으로 처리되었습니다."),
    CREATE_SUCCESS(HttpStatus.CREATED, "성공적으로 생성되었습니다."),
    UPDATE_SUCCESS(HttpStatus.OK, "성공적으로 수정되었습니다."),
    DELETE_SUCCESS(HttpStatus.OK, "성공적으로 삭제되었습니다."),

    // AUTH
    SIGNUP_SUCCESS(HttpStatus.CREATED, "회원 가입에 성공했습니다."),
    EMAIL_SEND_SUCCESS(HttpStatus.OK, "인증번호가 발송되었습니다."),
    EMAIL_VERIFY_SUCCESS(HttpStatus.OK, "이메일 인증에 성공했습니다."),
    LOGIN_SUCCESS(HttpStatus.OK, "로그인에 성공했습니다."),
    LOGOUT_SUCCESS(HttpStatus.OK, "로그아웃에 성공했습니다.");

    private final HttpStatus status;
    private final String message;
}
