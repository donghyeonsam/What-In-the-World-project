package com.ssafy.witw.common.exception;

import com.ssafy.witw.common.response.BaseResponse;
import com.ssafy.witw.common.response.ErrorCode;
import lombok.extern.slf4j.Slf4j;
import jakarta.validation.ConstraintViolationException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.web.HttpMediaTypeNotAcceptableException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.NoHandlerFoundException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

import java.util.Set;

@RestControllerAdvice
@Slf4j
public class GlobalExceptionHandler {

    @ExceptionHandler({MethodArgumentNotValidException.class, ConstraintViolationException.class,
            MissingServletRequestParameterException.class})
    protected ResponseEntity<BaseResponse<Void>> handleInvalidInput(Exception e) {
        return BaseResponse.error(ErrorCode.INVALID_INPUT_VALUE);
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    protected ResponseEntity<BaseResponse<Void>> handleMethodValidation(HandlerMethodValidationException e) {
        if (e.isForReturnValue()) {
            return handleException(e);
        }
        return BaseResponse.error(ErrorCode.INVALID_INPUT_VALUE);
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    protected ResponseEntity<BaseResponse<Void>> handleTypeMismatch(MethodArgumentTypeMismatchException e) {
        return BaseResponse.error(ErrorCode.METHOD_ARGUMENT_TYPE_MISMATCH);
    }

    @ExceptionHandler({NoResourceFoundException.class, NoHandlerFoundException.class})
    protected ResponseEntity<BaseResponse<Void>> handleNotFound(Exception e) {
        return BaseResponse.error(ErrorCode.RESOURCE_NOT_FOUND);
    }

    @ExceptionHandler(HttpRequestMethodNotSupportedException.class)
    protected ResponseEntity<BaseResponse<Void>> handleMethodNotAllowed(HttpRequestMethodNotSupportedException e) {
        HttpHeaders headers = new HttpHeaders();
        Set<HttpMethod> allowedMethods = e.getSupportedHttpMethods();
        if (allowedMethods != null) {
            headers.setAllow(allowedMethods);
        }
        var response = BaseResponse.<Void>error(ErrorCode.METHOD_NOT_ALLOWED);
        return new ResponseEntity<>(response.getBody(), headers, response.getStatusCode());
    }

    @ExceptionHandler(HttpMediaTypeNotAcceptableException.class)
    protected ResponseEntity<Void> handleNotAcceptable(HttpMediaTypeNotAcceptableException e) {
        return ResponseEntity.status(e.getStatusCode()).build();
    }

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
