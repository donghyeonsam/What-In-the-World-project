package com.ssafy.witw.domain.interest.dao;

import com.ssafy.witw.domain.interest.entity.UserInterestTheme;
import com.ssafy.witw.domain.interest.entity.UserInterestThemeId;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface UserInterestThemeRepository
        extends JpaRepository<UserInterestTheme, UserInterestThemeId> {

    boolean existsByUserIdAndThemeId(Long userId, Long themeId);

    //관심 테마 해제
    long deleteByUserIdAndThemeId(Long userId, Long themeId);

    // 관심 테마 목록은 theme 테이블의 이름까지 필요하므로 JOIN을 사용
    // 메서드 이름 규칙으로는 JOIN 을 표현할 수 없 어 JPQL을 직접 쓴다
    @Query("""
            select t.id as themeId, t.name as themeName
            from UserInterestTheme uit
            join Theme t on t.id = uit.themeId
            where uit.userId = :userId
            order by uit.createdAt
            """)
    List<InterestThemeRow> findInterestThemes(@Param("userId") Long userId);

    interface InterestThemeRow {
        Long getThemeId();
        String getThemeName();
    }

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query("""
    UPDATE UserInterestTheme i
    SET i.notificationEnabled = :enabled
    WHERE i.userId = :userId
      AND i.themeId = :themeId
    """)
    int updateNotificationEnabled(
            @Param("userId") Long userId,
            @Param("themeId") Long themeId,
            @Param("enabled") boolean enabled
    );
}
