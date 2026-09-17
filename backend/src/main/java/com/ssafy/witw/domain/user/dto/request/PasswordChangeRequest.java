package com.ssafy.witw.domain.user.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record PasswordChangeRequest (
        @NotBlank(message = "현재 비밀번호는 필수입니다.")
        @Size(min = 8, max = 72)
        String currentPassword,

        @NotBlank(message = "새 비밀번호는 필수입니다.")
        @Size(min = 8, max = 72, message = "새 비밀번호는 8자 이상 72자 이하여야합니다.")
        String newPassword
){

}
