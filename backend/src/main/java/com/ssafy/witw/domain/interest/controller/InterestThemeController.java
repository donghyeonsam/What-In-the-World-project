package com.ssafy.witw.domain.interest.controller;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.BaseResponse;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.common.response.SuccessCode;
import com.ssafy.witw.domain.interest.dto.request.InterestThemeAddRequest;
import com.ssafy.witw.domain.interest.dto.response.InterestThemeResponse;
import com.ssafy.witw.domain.interest.service.InterestThemeService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

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
        Long userId = resolveUserId(httpRequest);

        interestThemeService.addInterestTheme(userId, request);

        return BaseResponse.success(SuccessCode.CREATE_SUCCESS);
    }

    @GetMapping
    @Operation(summary= "관심 테마 목록 조회", description = "로그인한 사용자가 등록한 관심 테마를 등록순으로 조회한다.")
    public ResponseEntity<BaseResponse<List<InterestThemeResponse>>> getInterestThemes(
            HttpServletRequest httpRequest
    ){
        Long userId = resolveUserId(httpRequest);

        List<InterestThemeResponse> themes = interestThemeService.getInterestThemes(userId);

        return BaseResponse.success(SuccessCode.REQUEST_SUCCESS, themes);
    }

    @DeleteMapping("/{themeId}")
    @Operation(summary = "관심 테마 해제", description = "등록돼 있지 않은 테마를 해제해도 성공으로 처리한다.")
    public ResponseEntity<BaseResponse<Void>> removeInterestTheme(
            @PathVariable("themeId") Long themeId, HttpServletRequest httpRequest
    ){
        Long userId = resolveUserId(httpRequest);

        interestThemeService.removeInterestTheme(userId, themeId);

        return BaseResponse.success(SuccessCode.DELETE_SUCCESS);
    }

    // 세션에서 로그인 사용자 id 를 꺼낸다. 없으면 401.
    private Long resolveUserId(HttpServletRequest httpRequest){
        HttpSession session = httpRequest.getSession(false);

        if(session == null) throw new GlobalException(ErrorCode.UNAUTHORIZED);

        Object attribute = session.getAttribute("userId");

        if(!(attribute instanceof Long userId)) throw new GlobalException(ErrorCode.UNAUTHORIZED);

        return userId;
    }
}
