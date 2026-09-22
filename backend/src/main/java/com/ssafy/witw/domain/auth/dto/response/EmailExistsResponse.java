package com.ssafy.witw.domain.auth.dto.response;

public record EmailExistsResponse(
        boolean isDuplicate
) {
}
