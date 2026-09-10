package com.ssafy.witw.domain.auth.service;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.domain.auth.dto.EmailExistsResponse;
import com.ssafy.witw.domain.user.dao.UserRepository;
import com.ssafy.witw.domain.auth.dto.SignupRequest;
import com.ssafy.witw.domain.user.entity.User;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Locale;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class AuthService {
    private final UserRepository userRepository;
    private final PasswordEncoder passwordEncoder;

    // 회원가입
    @Transactional
    public void signup(SignupRequest request){
        String email = normalizeEmail(request.email());

        validateDuplicateEmail(email);

        String passwordHash = passwordEncoder.encode(request.password());

        User user = User.createLocal(email, passwordHash);

        userRepository.save(user);

    }

    private void validateDuplicateEmail(String email) {
        if(userRepository.existsByEmailIgnoreCase(email)){
            throw new GlobalException(ErrorCode.EMAIL_DUPLICATED);
        }
    }

    private String normalizeEmail(String email) {
        return email.trim().toLowerCase(Locale.ROOT);
    }

    public EmailExistsResponse checkEmailExists(String email){
        String normalizeEmail = normalizeEmail(email);
        boolean isDuplicate = userRepository.existsByEmailIgnoreCase(normalizeEmail);

        return new EmailExistsResponse(isDuplicate);
    }

}
