package com.ssafy.witw.domain.interest.service;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.domain.interest.dao.UserInterestThemeRepository;
import com.ssafy.witw.domain.interest.dto.request.InterestThemeAddRequest;
import com.ssafy.witw.domain.interest.entity.UserInterestTheme;
import com.ssafy.witw.domain.theme.dao.ThemeRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class InterestThemeService {

    private final UserInterestThemeRepository userInterestThemeRepository;
    private final ThemeRepository themeRepository;

    @Transactional
    public void addInterestTheme(Long userId, InterestThemeAddRequest request){
        Long themeId = request.themeId();

        if(!themeRepository.existsById(themeId))
            throw new GlobalException(ErrorCode.THEME_NOT_FOUND);

        if(userInterestThemeRepository.existsByUserIdAndThemeId(userId, themeId))
            throw new GlobalException(ErrorCode.INTEREST_THEME_DUPLICATED);

        userInterestThemeRepository.save(UserInterestTheme.create(userId, themeId));
    }
}
