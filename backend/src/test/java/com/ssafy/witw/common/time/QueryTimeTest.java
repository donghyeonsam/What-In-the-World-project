package com.ssafy.witw.common.time;

import com.ssafy.witw.common.exception.GlobalException;
import org.junit.jupiter.api.Test;

import java.time.LocalDateTime;
import java.time.OffsetDateTime;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class QueryTimeTest {
    @Test
    void convertsOffsetsToTheSameKstTime() {
        var expected = LocalDateTime.of(2025, 9, 10, 10, 50);
        assertThat(QueryTime.resolve(OffsetDateTime.parse("2025-09-10T01:50:00Z"))).isEqualTo(expected);
        assertThat(QueryTime.resolve(OffsetDateTime.parse("2025-09-10T10:50:00+09:00"))).isEqualTo(expected);
    }

    @Test
    void defaultsToCurrentKstTime() {
        var before = QueryTime.now();
        var resolved = QueryTime.resolve(null);
        assertThat(resolved).isBetween(before, QueryTime.now());
    }

    @Test
    void rejectsFutureTime() {
        assertThatThrownBy(() -> QueryTime.resolve(OffsetDateTime.now().plusDays(1)))
                .isInstanceOf(GlobalException.class);
    }
}
