package com.ssafy.witw.common.response;

import com.fasterxml.jackson.annotation.JsonInclude;
import jakarta.validation.constraints.NotNull;
import lombok.AccessLevel;
import lombok.Builder;
import org.springframework.http.ResponseEntity;


@JsonInclude(JsonInclude.Include.NON_NULL)
@Builder(access = AccessLevel.PRIVATE)
public record BaseResponse<T>(@NotNull Integer status, String code,  @NotNull String message, T data) {

    public static <T> ResponseEntity<BaseResponse<T>> success(final SuccessCode successCode) {
        return ResponseEntity.status(successCode.getStatus())
                        .body(BaseResponse.<T>builder()
                                .status(successCode.getStatus().value())
                                .message(successCode.getMessage())
                                .build());
    }

    public static <T> ResponseEntity<BaseResponse<T>> success(final SuccessCode successCode, final T data) {
        return ResponseEntity.status(successCode.getStatus())
                .body(BaseResponse.<T>builder()
                        .status(successCode.getStatus().value())
                        .message(successCode.getMessage())
                        .data(data)
                        .build());
    }

    public static <T> ResponseEntity<BaseResponse<T>> error(final ErrorCode errorCode) {
        return ResponseEntity.status(errorCode.getStatus())
                .body(BaseResponse.<T>builder()
                        .status(errorCode.getStatus().value())
                        .code(errorCode.getCode())
                        .message(errorCode.getMessage())
                        .build());
    }

    public static <T> ResponseEntity<BaseResponse<T>> error(final ErrorCode errorCode, final String message) {
        return ResponseEntity.status(errorCode.getStatus())
                .body(BaseResponse.<T>builder()
                        .status(errorCode.getStatus().value())
                        .code(errorCode.getCode())
                        .message(message)
                        .build());
    }

}
