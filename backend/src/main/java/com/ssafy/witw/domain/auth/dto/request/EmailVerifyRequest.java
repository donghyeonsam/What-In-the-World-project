package com.ssafy.witw.domain.auth.dto.request;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record EmailVerifyRequest (
        @NotBlank
        @Email
        @Size(max = 255)
        String email,

        @NotBlank
        @Pattern(
                regexp = "^[A-Za-z0-9]{7}$",
                message = "인증번호는 영문과 숫자로 구성된 7자리여야 합니다."
        )
        String code
) {
}
