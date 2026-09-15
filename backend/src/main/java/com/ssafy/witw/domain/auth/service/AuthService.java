package com.ssafy.witw.domain.auth.service;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.domain.auth.dto.request.LoginRequest;
import com.ssafy.witw.domain.auth.dto.response.EmailExistsResponse;
import com.ssafy.witw.domain.user.dao.UserRepository;
import com.ssafy.witw.domain.auth.dto.request.SignupRequest;
import com.ssafy.witw.domain.user.entity.AuthProvider;
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
    private final EmailVerificationService emailVerificationService;

    // 회원가입
    @Transactional
    public void signup(SignupRequest request){
        String email = normalizeEmail(request.email());

        User existingUser = userRepository.findByEmailIgnoreCase(email).orElse(null);

        if(existingUser != null && !existingUser.isWithdrawn())
            throw new GlobalException(ErrorCode.EMAIL_DUPLICATED);

        emailVerificationService.validateVerified(email);

        String passwordHash = passwordEncoder.encode(request.password());

        if(existingUser == null){
            User user = User.createLocal(email, passwordHash);

            userRepository.save(user);
        } else{
            existingUser.reactivateLocal(passwordHash);
        }

        userRepository.flush();

        emailVerificationService.clearVerified(email);

    }


    private String normalizeEmail(String email) {
        return email.trim().toLowerCase(Locale.ROOT);
    }

    public EmailExistsResponse checkEmailExists(String email){
        String normalizeEmail = normalizeEmail(email);

        boolean isDuplicate = userRepository.existsByEmailIgnoreCaseAndWithdrawnAtIsNull(normalizeEmail);

        return new EmailExistsResponse(isDuplicate);
    }

    public Long login(LoginRequest request){
        String email = normalizeEmail(request.email());

        User user = userRepository.findByEmailIgnoreCase(email)
                .orElseThrow(() -> new GlobalException(ErrorCode.LOGIN_FAILED));

        if(user.isWithdrawn()) throw new GlobalException(ErrorCode.LOGIN_FAILED);

        if(user.getAuthProvider() != AuthProvider.LOCAL) throw new GlobalException(ErrorCode.LOGIN_FAILED);

        if(user.getPasswordHash() == null || !passwordEncoder.matches(request.password(), user.getPasswordHash()))
            throw new GlobalException(ErrorCode.LOGIN_FAILED);

        return user.getId();
    }

}
