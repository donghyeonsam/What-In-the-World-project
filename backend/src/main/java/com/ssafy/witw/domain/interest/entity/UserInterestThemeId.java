package com.ssafy.witw.domain.interest.entity;

import lombok.EqualsAndHashCode;
import lombok.NoArgsConstructor;

import java.io.Serializable;

@EqualsAndHashCode
@NoArgsConstructor
public class UserInterestThemeId implements Serializable {

    private Long userId;
    private Long themeId;

    public UserInterestThemeId(Long userId, Long themeId) {
        this.userId = userId;
        this.themeId = themeId;
    }
}
