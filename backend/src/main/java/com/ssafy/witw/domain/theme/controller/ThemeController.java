package com.ssafy.witw.domain.theme.controller;

import com.ssafy.witw.common.response.BaseResponse;
import com.ssafy.witw.common.response.SuccessCode;
import com.ssafy.witw.domain.theme.dto.FieldThemesResponse;
import com.ssafy.witw.domain.theme.service.ThemeService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/themes")
public class ThemeController {
    private final ThemeService themeService;

    @GetMapping("/by-field")
    public ResponseEntity<BaseResponse<List<FieldThemesResponse>>> getThemesByField() {
        return BaseResponse.success(SuccessCode.REQUEST_SUCCESS, themeService.getThemesByField());
    }
}
