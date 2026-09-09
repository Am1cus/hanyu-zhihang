package com.coldaviation.config;

import com.coldaviation.websocket.TelemetryWebSocketHandler;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

/**
 * WebSocket 配置 - 用于实时推送无人机遥测数据
 */
@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {

    private final ObjectMapper objectMapper;
    private final com.coldaviation.repository.ExperimentRepository experiments;

    public WebSocketConfig(ObjectMapper objectMapper, com.coldaviation.repository.ExperimentRepository experiments) {
        this.objectMapper = objectMapper;
        this.experiments = experiments;
    }

    @Bean
    public TelemetryWebSocketHandler telemetryWebSocketHandler() {
        return new TelemetryWebSocketHandler(objectMapper, experiments::latestSnapshot);
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(telemetryWebSocketHandler(), "/ws/telemetry")
                .setAllowedOrigins("*");
    }
}
