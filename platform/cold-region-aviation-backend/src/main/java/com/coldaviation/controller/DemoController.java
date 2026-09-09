package com.coldaviation.controller;

import com.coldaviation.common.Result;
import com.coldaviation.service.AiPredictionService;
import com.coldaviation.service.TelemetryService;
import com.coldaviation.websocket.TelemetryWebSocketHandler;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 视频录制专用接口。仅在 demo 配置下加载，生产环境不会暴露数据重置能力。
 */
@Profile("demo")
@RestController
@RequestMapping("/api/demo")
public class DemoController {

    private final JdbcTemplate jdbcTemplate;
    private final TelemetryService telemetryService;
    private final TelemetryWebSocketHandler webSocketHandler;
    private final AiPredictionService aiPredictionService;

    public DemoController(JdbcTemplate jdbcTemplate,
                          TelemetryService telemetryService,
                          TelemetryWebSocketHandler webSocketHandler,
                          AiPredictionService aiPredictionService) {
        this.jdbcTemplate = jdbcTemplate;
        this.telemetryService = telemetryService;
        this.webSocketHandler = webSocketHandler;
        this.aiPredictionService = aiPredictionService;
    }

    @GetMapping("/lstm-capacity")
    public Result<Map<String, Object>> runCapacityValidation(
            @RequestParam(defaultValue = "0") int caseIndex) {
        return Result.success(aiPredictionService.predictCapacityValidationCase(caseIndex));
    }

    @PostMapping("/reset")
    public Result<Map<String,Object>> resetDemoData() {
        telemetryService.resetRuntimeState();
        webSocketHandler.broadcast(Map.of("type","demo-reset","serverTime",LocalDateTime.now()));
        return Result.success("仅重置实时视图，所有历史记录均保留",Map.of(
            "telemetryRows",0,"warningRows",0,"historyPreserved",true,
            "websocketConnections",webSocketHandler.getConnectionCount()));
    }
}
