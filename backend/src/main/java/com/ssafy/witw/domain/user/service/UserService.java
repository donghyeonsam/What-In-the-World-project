package com.ssafy.witw.domain.user.service;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.domain.user.dao.UserRepository;
import com.ssafy.witw.domain.user.dto.request.WithdrawRequest;
import com.ssafy.witw.domain.user.dto.response.UserResponse;
import com.ssafy.witw.domain.user.entity.AuthProvider;
import com.ssafy.witw.domain.user.entity.User;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class UserService {

    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;

    @Transactional
    public void withdraw(Long userId, WithdrawRequest request){
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new GlobalException(ErrorCode.UNAUTHORIZED));

        if(user.isWithdrawn()) throw new GlobalException(ErrorCode.UNAUTHORIZED);

        if(user.getAuthProvider() != AuthProvider.LOCAL || user.getPasswordHash() == null
                || !passwordEncoder.matches(request.password(), user.getPasswordHash())){
            throw new GlobalException(ErrorCode.CURRENT_PASSWORD_INVALID);
        }

        user.withdraw();
    }

    public UserResponse getCurrentUser(Long userId){
        User user = userRepository.findById(userId)
                .orElseThrow(() -> new GlobalException(ErrorCode.UNAUTHORIZED));

        if(user.isWithdrawn()) throw new GlobalException(ErrorCode.UNAUTHORIZED);

        return UserResponse.from(user);
    }



}
