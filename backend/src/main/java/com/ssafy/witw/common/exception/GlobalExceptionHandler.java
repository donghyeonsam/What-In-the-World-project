package com.ssafy.witw.common.exception;

import com.ssafy.witw.common.response.BaseResponse;
import com.ssafy.witw.common.response.ErrorCode;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
@Slf4j
public class GlobalExceptionHandler {

    @ExceptionHandler(GlobalException.class)
    protected ResponseEntity<BaseResponse<Void>> handleGlobalException(GlobalException e) {

        HttpStatusCode statusCode = e.getErrorCode().getStatus();
        String code = e.getErrorCode().getCode();
        logByStatus(statusCode, code, e);

        return BaseResponse.error(e.getErrorCode());
    }

    @ExceptionHandler(Exception.class)
    protected ResponseEntity<BaseResponse<Void>> handleException(Exception e) {

        log.error(e.getMessage(), e);
        return BaseResponse.error(ErrorCode.INTERNAL_SERVER_ERROR);
    }

    private void logByStatus(HttpStatusCode statusCode, String errorCode, GlobalException e) {

        if(statusCode.is5xxServerError()) {
            log.error(e.getMessage(), e);
            return;
        }

        log.warn("{}: [{},{}] {}", e.getClass().getSimpleName(), statusCode.value(), errorCode, e.getMessage());
    }

}
