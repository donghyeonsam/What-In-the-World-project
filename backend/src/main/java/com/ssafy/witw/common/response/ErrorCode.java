package com.ssafy.witw.common.response;

import lombok.AccessLevel;
import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;

@Getter
@RequiredArgsConstructor(access = AccessLevel.PRIVATE)
public enum ErrorCode {

    // COMMON
    INVALID_INPUT_VALUE(HttpStatus.BAD_REQUEST, "CO01", "유효하지 않은 입력 값입니다."),
    INVALID_TYPE_VALUE(HttpStatus.BAD_REQUEST, "CO02", "유효하지 않은 타입 값입니다."),
    ENTITY_NOT_FOUND(HttpStatus.NOT_FOUND, "CO03", "해당 엔티티를 찾을 수 없습니다."),
    METHOD_NOT_ALLOWED(HttpStatus.METHOD_NOT_ALLOWED, "CO04", "지원하지 않는 HTTP Method 입니다."),
    METHOD_NOT_SUPPORTED(HttpStatus.UNSUPPORTED_MEDIA_TYPE, "CO05", "지원하지 않는 Content-Type 입니다."),
    METHOD_ARGUMENT_TYPE_MISMATCH(HttpStatus.BAD_REQUEST, "CO06", "요청 인자의 타입이 올바르지 않습니다."),
    ACCESS_DENIED(HttpStatus.FORBIDDEN, "CO07", "접근 권한이 없습니다."),
    UNAUTHORIZED(HttpStatus.UNAUTHORIZED, "CO08", "인증 정보가 유효하지 않습니다."),
    CONSTRAINT_VIOLATION(HttpStatus.CONFLICT, "CO09", "데이터베이스 제약 조건 위반입니다."),
    BAD_SQL_GRAMMAR(HttpStatus.INTERNAL_SERVER_ERROR, "CO10", "잘못된 SQL 문법 오류가 발생했습니다."),
    REQUEST_TOO_LARGE(HttpStatus.PAYLOAD_TOO_LARGE, "CO11", "요청의 크기가 너무 큽니다."),
    TOO_MANY_REQUESTS(HttpStatus.TOO_MANY_REQUESTS, "CO12", "너무 많은 요청을 보냈습니다. 잠시 후 다시 시도해주세요."),
    RESOURCE_NOT_FOUND(HttpStatus.NOT_FOUND, "CO13", "요청하신 리소스를 찾을 수 없습니다."),
    INTERNAL_SERVER_ERROR(HttpStatus.INTERNAL_SERVER_ERROR, "CO99", "서버 내부 오류가 발생했습니다. 관리자에게 문의하세요."),

    // THEME
    THEME_NOT_FOUND(HttpStatus.NOT_FOUND, "TH01", "테마를 찾을 수 없습니다."),

    // COUNTRY
    COUNTRY_NOT_FOUND(HttpStatus.NOT_FOUND, "CT01", "국가를 찾을 수 없습니다."),

    // AUTH
    EMAIL_DUPLICATED(HttpStatus.CONFLICT, "AU01", "이미 사용 중인 이메일입니다."),
    EMAIL_SEND_FAILED(HttpStatus.INTERNAL_SERVER_ERROR, "AU02", "인증번호 이메일 발송에 실패했습니다."),
    EMAIL_SEND_LIMIT_EXCEEDED(HttpStatus.TOO_MANY_REQUESTS, "AU03", "이메일 인증번호 발송 횟수를 초과했습니다."),
    EMAIL_CODE_EXPIRED(HttpStatus.GONE, "AU04", "인증번호가 만료되었거나 존재하지 않습니다."),
    EMAIL_CODE_INVALID(HttpStatus.BAD_REQUEST, "AU05", "인증번호가 일치하지 않습니다."),
    EMAIL_VERIFY_LIMIT_EXCEEDED(HttpStatus.TOO_MANY_REQUESTS, "AU06", "이메일 인증 시도 횟수를 초과했습니다."),
    EMAIL_NOT_VERIFIED(HttpStatus.FORBIDDEN, "AU07", "이메일 인증이 완료되지 않았습니다."),
    LOGIN_FAILED(HttpStatus.UNAUTHORIZED, "AU08", "이메일 또는 비밀번호가 올바르지 않습니다."),
    CURRENT_PASSWORD_INVALID(HttpStatus.BAD_REQUEST, "AU09", "현재 비밀번호가 올바르지 않습니다."),
    PASSWORD_RESET_NOT_VERIFIED(HttpStatus.UNAUTHORIZED, "AU10", "비밀번호 재설정을 위한 이메일 인증이 필요합니다."),
    SSAFY_AUTH_FAILED(HttpStatus.UNAUTHORIZED, "AU11", "SSAFY 인증에 실패했습니다."),
    AUTH_PROVIDER_CONFLICT(HttpStatus.CONFLICT, "AU12", "이미 다른 방식으로 가입된 이메일입니다."),
    SSAFY_SERVER_ERROR(HttpStatus.BAD_GATEWAY, "AU13", "SSAFY 인증 서버와 통신할 수 없습니다."),
    INTEREST_THEME_DUPLICATED(HttpStatus.CONFLICT, "IN01", "이미 등록한 관심 테마입니다.");


    private final HttpStatus status;
    private final String code;
    private final String message;

}
