package com.ssafy.witw.domain.auth.service;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.domain.auth.dto.request.EmailRequest;
import com.ssafy.witw.domain.auth.dto.request.EmailVerifyRequest;
import com.ssafy.witw.domain.auth.dto.response.EmailSendResponse;
import com.ssafy.witw.domain.user.dao.UserRepository;
import com.ssafy.witw.domain.user.entity.AuthProvider;
import com.ssafy.witw.domain.user.entity.User;
import lombok.RequiredArgsConstructor;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.mail.MailException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.stereotype.Service;
import org.springframework.mail.javamail.JavaMailSender;

import java.security.SecureRandom;
import java.time.Duration;
import java.util.Locale;

@Service
@RequiredArgsConstructor
public class EmailVerificationService {

    // Redis 저장 시 활용되는 접두사
    // code : 이메일 인증 코드, send : 이메일 발송 횟수
    private static final String CODE_KEY_PREFIX = "auth:email:signup:code:";
    private static final String SEND_KEY_PREFIX = "auth:email:signup:send:";

    // try : 이메일 인증 시도 횟수, done : 이메일 성공 여부 저장
    private static final String TRY_KEY_PREFIX = "auth:email:signup:try:";
    private static final String DONE_KEY_PREFIX = "auth:email:signup:done:";

    // 비밀번호 재설정 인증번호 발송
    private static final String PASSWORD_CODE_KEY_PREFIX = "auth:email:password:code:";
    private static final String PASSWORD_SEND_KEY_PREFIX = "auth:email:password:send:";
    private static final String PASSWORD_TRY_KEY_PREFIX = "auth:email:password:try:";

    // 인증 코드 (알파벳 + 영어 7자리)
    private static final String CODE_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    private static final int CODE_LENGTH = 7;

    // Redis TTL과 timeLimit이 동일한 상수 사용
    private static final int TIME_LIMIT_SECONDS = 300;

    // 1시간 내로 특정 이메일 주소에 보낼 수 있는 횟수 (1시간 유지)
    private static final int SEND_LIMIT = 5;
    private static final Duration SEND_LIMIT_TTL = Duration.ofHours(1);

    // 이메일 인증 최대 횟수 5회로 제한, 시도 횟수 TTL 또한 이메일 코드 TTL과 동일하게 설정
    // 인증을 성공하게 된다면 해당 이메일 인증 성공 여부를 30분 동안 저장
    private static final int TRY_LIMIT = 5;
    private static final Duration TRY_LIMIT_TTL = Duration.ofSeconds(TIME_LIMIT_SECONDS);
    private static final Duration DONE_TTL = Duration.ofMinutes(30);

    private final UserRepository userRepository;
    private final StringRedisTemplate redisTemplate;
    private final JavaMailSender mailSender;

    private final SecureRandom secureRandom = new SecureRandom();

    public EmailSendResponse sendCode(EmailRequest request){
        String email = request.email().trim().toLowerCase(Locale.ROOT);

        if(userRepository.existsByEmailIgnoreCaseAndWithdrawnAtIsNull(email))
            throw new GlobalException(ErrorCode.EMAIL_DUPLICATED);

        increaseSendCount(email, SEND_KEY_PREFIX);

        String code = generateCode();
        String codeKey = CODE_KEY_PREFIX + email;

        redisTemplate.opsForValue().set(codeKey, code, Duration.ofSeconds(TIME_LIMIT_SECONDS));

        // 재발송 시 이전 코드에 대한 시도 횟수 초기화
        redisTemplate.delete(TRY_KEY_PREFIX + email);

        try {
            sendEmail(email, code);
        } catch (MailException exception){
            redisTemplate.delete(codeKey);
            throw new GlobalException(ErrorCode.EMAIL_SEND_FAILED, exception);
        }

        return new EmailSendResponse(TIME_LIMIT_SECONDS);
    }

    public void verifyCode(EmailVerifyRequest request){
        String email = request.email().trim().toLowerCase(Locale.ROOT);
        String inputCode = request.code().trim().toUpperCase(Locale.ROOT);

        String codeKey = CODE_KEY_PREFIX + email;
        String tryKey = TRY_KEY_PREFIX + email;
        String doneKey = DONE_KEY_PREFIX + email;

        String savedCode = redisTemplate.opsForValue().get(codeKey);

        if(savedCode == null) throw new GlobalException(ErrorCode.EMAIL_CODE_EXPIRED);

        increaseTryCount(email, codeKey, TRY_KEY_PREFIX);

        if(!savedCode.equals(inputCode)) throw new GlobalException(ErrorCode.EMAIL_CODE_INVALID);

        redisTemplate.opsForValue().set(doneKey, "true", DONE_TTL);

        redisTemplate.delete(codeKey);
        redisTemplate.delete(tryKey);
    }

    public void validateVerified(String email){
        String normalizedEmail = email.trim().toLowerCase(Locale.ROOT);

        Boolean verified = redisTemplate.hasKey(DONE_KEY_PREFIX + normalizedEmail);

        if(!Boolean.TRUE.equals(verified)) throw new GlobalException(ErrorCode.EMAIL_NOT_VERIFIED);

    }

    public void clearVerified(String email){
        String normalizedEmail = email.trim().toLowerCase(Locale.ROOT);

        redisTemplate.delete(DONE_KEY_PREFIX + normalizedEmail);
    }

    public EmailSendResponse sendPasswordResetCode(EmailRequest request){
        String email = request.email().trim().toLowerCase(Locale.ROOT);

        User user = userRepository.findByEmailIgnoreCase(email).orElse(null);

        if(user == null || user.isWithdrawn() || user.getAuthProvider() != AuthProvider.LOCAL)
            return new EmailSendResponse(TIME_LIMIT_SECONDS);

        increaseSendCount(email, PASSWORD_SEND_KEY_PREFIX);

        String code = generateCode();
        String codeKey = PASSWORD_CODE_KEY_PREFIX + email;

        redisTemplate.opsForValue().set(codeKey, code, Duration.ofSeconds(TIME_LIMIT_SECONDS));

        redisTemplate.delete(PASSWORD_TRY_KEY_PREFIX + email);

        try {
            sendPasswordResetEmail(email, code);
        } catch (MailException exception){
            redisTemplate.delete(codeKey);
            throw new GlobalException(ErrorCode.EMAIL_SEND_FAILED, exception);
        }

        return new EmailSendResponse(TIME_LIMIT_SECONDS);

    }

    public String verifyPasswordResetCode(EmailVerifyRequest request){
        String email = request.email().trim().toLowerCase(Locale.ROOT);

        String inputCode = request.code().trim().toUpperCase(Locale.ROOT);

        String codeKey = PASSWORD_CODE_KEY_PREFIX + email;

        String tryKey = PASSWORD_TRY_KEY_PREFIX + email;

        String savedCode = redisTemplate.opsForValue().get(codeKey);

        if(savedCode == null) throw new GlobalException(ErrorCode.EMAIL_CODE_EXPIRED);

        increaseTryCount(email, codeKey, PASSWORD_TRY_KEY_PREFIX);

        if(!savedCode.equals(inputCode)) throw new GlobalException(ErrorCode.EMAIL_CODE_INVALID);

        redisTemplate.delete(codeKey);
        redisTemplate.delete(tryKey);

        return email;
    }

    private void sendPasswordResetEmail(String email, String code) {
        SimpleMailMessage message = new SimpleMailMessage();

        message.setTo(email);
        message.setSubject("[WITW] 비밀번호 재설정 인증번호");
        message.setText("비밀번호 재설정 인증번호는 [" + code + "]입니다. \n"
                + "인증번호는 5분안에 입력해주세요.");
        mailSender.send(message);
    }

    private void increaseSendCount(String email, String keyPrefix) {
        String key = keyPrefix + email;

        Long count = redisTemplate.opsForValue().increment(key);

        if(count == null) throw new GlobalException(ErrorCode.INTERNAL_SERVER_ERROR);

        // 1이면 첫 발송이므로 TTL설정
        if(count == 1L) redisTemplate.expire(key, SEND_LIMIT_TTL);

        // SEND_LIMIT을 넘길 경우 429 발생
        if(count > SEND_LIMIT) throw new GlobalException(ErrorCode.EMAIL_SEND_LIMIT_EXCEEDED);


    }

    private String generateCode() {
        StringBuilder sb = new StringBuilder(CODE_LENGTH);
        for(int i = 0; i < CODE_LENGTH; i++){
            sb.append(CODE_CHARS.charAt(secureRandom.nextInt(CODE_CHARS.length())));
        }
        return sb.toString();
    }

    private void sendEmail(String email, String code) {
        SimpleMailMessage message = new SimpleMailMessage();

        message.setTo(email);
        message.setSubject("[WITW] 이메일 인증번호");
        message.setText("인증번호는 [" + code + "]입니다. \n"
        + "인증번호는 5분안에 입력해주세요.");

        mailSender.send(message);
    }

    private void increaseTryCount(String email, String codeKey, String tryKeyPrefix) {
        String tryKey = tryKeyPrefix + email;
        Long count = redisTemplate.opsForValue().increment(tryKey);

        if (count == null) throw new GlobalException(ErrorCode.INTERNAL_SERVER_ERROR);

        if (count == 1L) redisTemplate.expire(tryKey, TRY_LIMIT_TTL);

        if (count > TRY_LIMIT) {
            redisTemplate.delete(codeKey);
            throw new GlobalException(ErrorCode.EMAIL_VERIFY_LIMIT_EXCEEDED);
        }
    }


}
