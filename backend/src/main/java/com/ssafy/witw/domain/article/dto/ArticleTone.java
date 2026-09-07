package com.ssafy.witw.domain.article.dto;

import java.math.BigDecimal;

public enum ArticleTone {
    POSITIVE,
    NEUTRAL,
    NEGATIVE;

    public static ArticleTone fromScore(BigDecimal score) {
        if (score == null) {
            return NEUTRAL;
        }
        if (score.compareTo(BigDecimal.valueOf(33)) <= 0) {
            return NEGATIVE;
        }
        if (score.compareTo(BigDecimal.valueOf(66)) <= 0) {
            return NEUTRAL;
        }
        return POSITIVE;
    }
}
