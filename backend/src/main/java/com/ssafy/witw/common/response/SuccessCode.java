package com.ssafy.witw.common.response;

import lombok.AccessLevel;
import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;

@Getter
@RequiredArgsConstructor(access = AccessLevel.PRIVATE)
public enum SuccessCode {

    // Common
    REQUEST_SUCCESS(HttpStatus.OK, "요청이 성공적으로 처리되었습니다."),
    CREATE_SUCCESS(HttpStatus.CREATED, "성공적으로 생성되었습니다."),
    UPDATE_SUCCESS(HttpStatus.OK, "성공적으로 수정되었습니다."),
    DELETE_SUCCESS(HttpStatus.OK, "성공적으로 삭제되었습니다.");

    private final HttpStatus status;
    private final String message;
}
