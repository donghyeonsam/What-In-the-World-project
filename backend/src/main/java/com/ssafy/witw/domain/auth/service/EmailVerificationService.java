package com.ssafy.witw.domain.auth.service;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.domain.auth.dto.request.EmailRequest;
import com.ssafy.witw.domain.auth.dto.response.EmailSendResponse;
import com.ssafy.witw.domain.user.dao.UserRepository;
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

    // 인증 코드 (알파벳 + 영어 7자리)
    private static final String CODE_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    private static final int CODE_LENGTH = 7;

    // Redis TTL과 timeLimit이 동일한 상수 사용
    private static final int TIME_LIMIT_SECONDS = 300;

    // 1시간 내로 특정 이메일 주소에 보낼 수 있는 횟수 (1시간 유지)
    private static final int SEND_LIMIT = 5;
    private static final Duration SEND_LIMIT_TTL = Duration.ofHours(1);


    private final UserRepository userRepository;
    private final StringRedisTemplate redisTemplate;
    private final JavaMailSender mailSender;

    private final SecureRandom secureRandom = new SecureRandom();

    public EmailSendResponse sendCode(EmailRequest request){
        String email = request.email().trim().toLowerCase(Locale.ROOT);

        if(userRepository.existsByEmailIgnoreCase(email)){ throw new GlobalException(ErrorCode.EMAIL_DUPLICATED); }

        increaseSendCount(email);

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

    private void increaseSendCount(String email) {
        String key = SEND_KEY_PREFIX + email;

        Long count = redisTemplate.opsForValue().increment(key);

        if(count == null) throw new GlobalException(ErrorCode.INTERNAL_SERVER_ERROR);

        // 1이면 첫 발송이므로 TTL설정
        if(count == 1L) redisTemplate.expire(key, SEND_LIMIT_TTL);

        // SEND_LIMIT을 넘길 경우 429 발생
        if(count > SEND_LIMIT){
            throw new GlobalException(ErrorCode.EMAIL_SEND_LIMIT_EXCEEDED);
        }

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


}
