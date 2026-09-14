package com.ssafy.witw.domain.user.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record WithdrawRequest (
        @NotBlank
        @Size(min = 8, max = 72)
        String password
){
}
