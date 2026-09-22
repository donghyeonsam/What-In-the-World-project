package com.ssafy.witw.domain.auth.dto.request;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record EmailRequest (
        @NotBlank
        @Email
        @Size(max = 255)
        String email
){
}
