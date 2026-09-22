package com.ssafy.witw.common.time;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;

import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;

/** API 시각을 기존 DB의 KST timestamp 기준으로 변환한다. */
public final class QueryTime {
    private static final ZoneId KST = ZoneId.of("Asia/Seoul");

    private QueryTime() {
    }

    public static LocalDateTime now() {
        return LocalDateTime.now(KST);
    }

    public static LocalDateTime resolve(OffsetDateTime asOf) {
        LocalDateTime now = now();
        if (asOf == null) return now;
        LocalDateTime resolved = asOf.atZoneSameInstant(KST).toLocalDateTime();
        if (resolved.isAfter(now)) {
            throw new GlobalException(ErrorCode.INVALID_INPUT_VALUE);
        }
        return resolved;
    }
}
