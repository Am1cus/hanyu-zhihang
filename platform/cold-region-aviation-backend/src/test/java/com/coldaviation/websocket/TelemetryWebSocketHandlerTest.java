package com.coldaviation.websocket;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class TelemetryWebSocketHandlerTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void newConnectionsReceivePreviousPredictionsWithOriginalServerTime() throws Exception {
        var handler = new TelemetryWebSocketHandler(mapper);
        handler.broadcast(Map.of("type", "telemetry", "serverTime", "2026-09-06T12:00:00",
                "telemetry", Map.of("droneId", 2), "prediction", Map.of("valid", true)));
        var session = mockSession("restore");
        handler.afterConnectionEstablished(session);
        var message = ArgumentCaptor.forClass(TextMessage.class);
        verify(session).sendMessage(message.capture());
        var payload = mapper.readTree(message.getValue().getPayload());
        assertEquals("snapshot", payload.get("type").asText());
        assertTrue(payload.get("events").get(0).get("prediction").get("valid").asBoolean());
        assertEquals("2026-09-06T12:00:00", payload.get("events").get(0).get("serverTime").asText());
        handler.afterConnectionClosed(session, CloseStatus.NORMAL);
    }

    @Test
    void resetRemovesReplayFromSnapshots() throws Exception {
        var handler = new TelemetryWebSocketHandler(mapper);
        handler.broadcast(Map.of("type", "telemetry", "telemetry", Map.of("droneId", 2)));
        handler.broadcast(Map.of("type", "demo-reset"));
        var session = mockSession("reset");
        handler.afterConnectionEstablished(session);
        var message = ArgumentCaptor.forClass(TextMessage.class);
        verify(session).sendMessage(message.capture());
        assertEquals(0, mapper.readTree(message.getValue().getPayload()).get("events").size());
        handler.afterConnectionClosed(session, CloseStatus.NORMAL);
    }

    @Test
    void snapshotHistoryIsBounded() throws Exception {
        var handler = new TelemetryWebSocketHandler(mapper);
        for (int i = 0; i < 1802; i++) handler.broadcast(Map.of("type", "telemetry", "sequence", i));
        var session = mockSession("bounded");
        handler.afterConnectionEstablished(session);
        var message = ArgumentCaptor.forClass(TextMessage.class);
        verify(session).sendMessage(message.capture());
        var events = mapper.readTree(message.getValue().getPayload()).get("events");
        assertEquals(1800, events.size());
        assertEquals(2, events.get(0).get("sequence").asInt());
        handler.afterConnectionClosed(session, CloseStatus.NORMAL);
    }

    private WebSocketSession mockSession(String id) {
        var session = mock(WebSocketSession.class);
        when(session.getId()).thenReturn(id);
        when(session.isOpen()).thenReturn(true);
        return session;
    }
}
