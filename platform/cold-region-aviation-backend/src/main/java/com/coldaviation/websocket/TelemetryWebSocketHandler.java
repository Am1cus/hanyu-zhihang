package com.coldaviation.websocket;

import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.io.IOException;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.Map;
import java.util.List;
import java.util.function.Supplier;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 遥测数据 WebSocket 处理器
 * 用于向前端实时推送无人机遥测数据
 */
@Slf4j
public class TelemetryWebSocketHandler extends TextWebSocketHandler {

    /** 存储所有已连接的 WebSocket 会话 */
    private static final ConcurrentHashMap<String, WebSocketSession> SESSIONS = new ConcurrentHashMap<>();

    private final ObjectMapper objectMapper;
    private final Supplier<List<Object>> durableSnapshot;
    private boolean displayCleared = false;
    // Bounded process-local history for reconnects, not a durable prediction archive.
    private final Deque<Object> recentEvents = new ArrayDeque<>();

    public TelemetryWebSocketHandler(ObjectMapper objectMapper) {
        this(objectMapper, null);
    }

    public TelemetryWebSocketHandler(ObjectMapper objectMapper, Supplier<List<Object>> durableSnapshot) {
        this.objectMapper = objectMapper;
        this.durableSnapshot = durableSnapshot;
    }

    @Override
    public synchronized void afterConnectionEstablished(WebSocketSession session) {
        SESSIONS.put(session.getId(), session);
        List<Object> events = displayCleared ? List.of() : durableSnapshot == null
                ? new ArrayList<>(recentEvents) : durableSnapshot.get();
        sendToSession(session.getId(), Map.of("type", "snapshot", "events", events));
        log.info("WebSocket 连接建立: sessionId={}, 当前连接数={}", session.getId(), SESSIONS.size());
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) {
        log.debug("收到WebSocket消息: sessionId={}, payload={}", session.getId(), message.getPayload());
        // 可以处理前端发来的订阅请求，例如订阅特定无人机的数据
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        SESSIONS.remove(session.getId());
        log.info("WebSocket 连接关闭: sessionId={}, status={}, 剩余连接数={}",
                session.getId(), status, SESSIONS.size());
    }

    @Override
    public void handleTransportError(WebSocketSession session, Throwable exception) {
        log.error("WebSocket 传输错误: sessionId={}, error={}", session.getId(), exception.getMessage());
        SESSIONS.remove(session.getId());
    }

    /**
     * 向所有连接的客户端广播遥测数据
     * @param data 遥测数据对象
     */
    public synchronized void broadcast(Object data) {
        if (data instanceof Map<?, ?> event) {
            if ("demo-reset".equals(event.get("type")) || "run-started".equals(event.get("type"))) {
                recentEvents.clear(); displayCleared = true;
            }
            if ("telemetry".equals(event.get("type"))) {
                displayCleared = false;
                recentEvents.addLast(data);
                while (recentEvents.size() > 1800) recentEvents.removeFirst();
            }
        }
        String jsonMessage;
        try {
            jsonMessage = objectMapper.writeValueAsString(data);
        } catch (Exception e) {
            log.error("序列化遥测数据失败: {}", e.getMessage());
            return;
        }

        TextMessage message = new TextMessage(jsonMessage);
        SESSIONS.values().forEach(session -> {
            if (session.isOpen()) {
                try {
                    session.sendMessage(message);
                } catch (IOException e) {
                    log.error("发送WebSocket消息失败: sessionId={}, error={}", session.getId(), e.getMessage());
                }
            }
        });
    }

    /**
     * 向指定会话发送消息
     */
    public synchronized void sendToSession(String sessionId, Object data) {
        WebSocketSession session = SESSIONS.get(sessionId);
        if (session != null && session.isOpen()) {
            try {
                String json = objectMapper.writeValueAsString(data);
                session.sendMessage(new TextMessage(json));
            } catch (IOException e) {
                log.error("发送消息失败: sessionId={}, error={}", sessionId, e.getMessage());
            }
        }
    }

    /**
     * 获取当前连接数
     */
    public int getConnectionCount() {
        return SESSIONS.size();
    }
}
