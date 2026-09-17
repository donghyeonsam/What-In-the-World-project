package com.ssafy.witw.domain.user.dto.response;

import com.ssafy.witw.domain.user.entity.AuthProvider;
import com.ssafy.witw.domain.user.entity.User;
import com.ssafy.witw.domain.user.entity.UserRole;

public record UserResponse (
        Long id,
        String email,
        AuthProvider authProvider,
        UserRole role
){
    public static UserResponse from(User user){
        return new UserResponse(
                user.getId(),
                user.getEmail(),
                user.getAuthProvider(),
                user.getRole()
        );
    }
}
