package com.ssafy.witw.domain.interest.dao;

import com.ssafy.witw.domain.interest.entity.UserInterestTheme;
import com.ssafy.witw.domain.interest.entity.UserInterestThemeId;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserInterestThemeRepository
        extends JpaRepository<UserInterestTheme, UserInterestThemeId> {

    boolean existsByUserIdAndThemeId(Long userId, Long themeId);
}
