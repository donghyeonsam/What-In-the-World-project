package com.ssafy.witw.domain.interest.service;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.domain.interest.dao.UserInterestThemeRepository;
import com.ssafy.witw.domain.interest.dto.request.InterestThemeAddRequest;
import com.ssafy.witw.domain.interest.dto.response.InterestThemeResponse;
import com.ssafy.witw.domain.interest.entity.UserInterestTheme;
import com.ssafy.witw.domain.theme.dao.ThemeRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

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

    //관심 테마 해제
    @Transactional
    public void removeInterestTheme(Long userId, Long themeId){
        userInterestThemeRepository.deleteByUserIdAndThemeId(userId, themeId);
    }

    // 관심 테마 목록 조회
    public List<InterestThemeResponse> getInterestThemes(Long userId){
        return userInterestThemeRepository.findInterestThemes(userId)
                .stream()
                .map(InterestThemeResponse::from)
                .toList();
    }
}
