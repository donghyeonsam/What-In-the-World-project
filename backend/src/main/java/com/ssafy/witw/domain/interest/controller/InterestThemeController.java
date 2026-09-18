package com.ssafy.witw.domain.interest.controller;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.BaseResponse;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.common.response.SuccessCode;
import com.ssafy.witw.domain.interest.dto.request.InterestThemeAddRequest;
import com.ssafy.witw.domain.interest.service.InterestThemeService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/v1/users/me/interests/themes")
@Tag(name = "관심 테마", description = "사용자 관심 테마 API")
public class InterestThemeController {

    private final InterestThemeService interestThemeService;

    @PostMapping
    @Operation(summary = "관심 테마 등록")
    public ResponseEntity<BaseResponse<Void>> addInterestTheme(
            @Valid @RequestBody InterestThemeAddRequest request, HttpServletRequest httpRequest
    ){
        HttpSession session = httpRequest.getSession(false);

        if(session == null) throw new GlobalException(ErrorCode.UNAUTHORIZED);

        Object attribute = session.getAttribute("userId");

        if(!(attribute instanceof Long userId)) throw new GlobalException(ErrorCode.UNAUTHORIZED);

        interestThemeService.addInterestTheme(userId, request);

        return BaseResponse.success(SuccessCode.CREATE_SUCCESS);
    }
}
