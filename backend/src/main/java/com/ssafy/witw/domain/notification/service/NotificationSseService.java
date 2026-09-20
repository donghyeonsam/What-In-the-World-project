package com.ssafy.witw.domain.notification.service;

import com.ssafy.witw.common.exception.GlobalException;
import com.ssafy.witw.common.response.ErrorCode;
import com.ssafy.witw.domain.user.dao.UserRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.session.Session;
import org.springframework.session.SessionRepository;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@Slf4j
@Service
@RequiredArgsConstructor
public class NotificationSseService {

    private static final long CONNECTION_TIMEOUT_MS = 5 * 60 * 1000L;

    private final UserRepository userRepository;
    private final SessionRepository<? extends Session> sessionRepository;

    private final Map<String, Connection> connections = new ConcurrentHashMap<>();

    private record Connection(
            Long userId,
            String sessionId,
            SseEmitter emitter
    ) {
    }

    public SseEmitter subscribe(Long userId, String sessionId) {
        var user = userRepository.findById(userId)
                .orElseThrow(() -> new GlobalException(ErrorCode.UNAUTHORIZED));

        if (user.isWithdrawn()) throw new GlobalException(ErrorCode.UNAUTHORIZED);


        SseEmitter emitter = new SseEmitter(CONNECTION_TIMEOUT_MS);
        String connectionId = UUID.randomUUID().toString();

        Connection connection = new Connection(
                userId,
                sessionId,
                emitter
        );

        emitter.onCompletion(() -> connections.remove(connectionId));
        emitter.onTimeout(() -> close(connectionId, connection));
        emitter.onError(error -> close(connectionId, connection));

        connections.put(connectionId, connection);

        try {
            emitter.send(SseEmitter.event()
                            .name("connected")
                            .data("connected")
                            .reconnectTime(3000)
            );
        } catch (IOException | IllegalStateException exception) {
            close(connectionId, connection);
        }

        return emitter;
    }

    @Scheduled(fixedDelay = 15000, initialDelay = 15000)
    public void heartbeat() {
        connections.forEach((connectionId, connection) -> {
            try {
                if (!isSessionValid(connection)) {
                    close(connectionId, connection);
                    return;
                }

                connection.emitter().send(
                        SseEmitter.event()
                                .name("heartbeat")
                                .data("ping")
                );
            } catch (IOException | IllegalStateException exception) {
                close(connectionId, connection);
            } catch (Exception exception) {
                // 세션 저장소 등에 문제가 있으면 연결을 닫는다.
                log.warn("SSE 연결 확인 중 오류가 발생했습니다.", exception);
                close(connectionId, connection);
            }
        });
    }

    private boolean isSessionValid(Connection connection) {
        Session session = sessionRepository.findById(connection.sessionId());

        if (session == null || session.isExpired()) return false;


        Object userId = session.getAttribute("userId");

        return connection.userId().equals(userId);
    }

    private void close(String connectionId, Connection connection) {
        if (connections.remove(connectionId, connection)) {
            connection.emitter().complete();
        }
    }
}