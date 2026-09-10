package com.ssafy.witw.domain.auth.dto;

public record EmailExistsResponse(
        boolean isDuplicate
) {
}
