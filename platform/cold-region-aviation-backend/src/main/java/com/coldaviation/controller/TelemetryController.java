package com.coldaviation.controller;

import com.coldaviation.common.Result;
import com.coldaviation.entity.TelemetryData;
import com.coldaviation.service.TelemetryService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 遥测数据控制器
 */
@Slf4j
@RestController
@RequestMapping("/api/telemetry")
public class TelemetryController {

    @Autowired
    private TelemetryService telemetryService;

    /** 上报遥测数据 */
    @PostMapping
    public Result<Boolean> report(@RequestBody TelemetryData data) {
        return Result.success(telemetryService.saveTelemetry(data));
    }

    /** 获取指定无人机的最新遥测数据 */
    @GetMapping("/latest/{droneId}")
    public Result<TelemetryData> getLatest(@PathVariable Long droneId) {
        return Result.success(telemetryService.getLatestByDroneId(droneId));
    }

    /** 获取实时遥测数据（从Redis缓存） */
    @GetMapping("/realtime/{droneId}")
    public Result<TelemetryData> getRealtime(@PathVariable Long droneId) {
        return Result.success(telemetryService.getRealtimeFromCache(droneId));
    }

    /** 查询历史遥测数据（按时间范围） */
    @GetMapping("/history/{droneId}")
    public Result<List<TelemetryData>> getHistory(
            @PathVariable Long droneId,
            @RequestParam @DateTimeFormat(pattern = "yyyy-MM-dd HH:mm:ss") LocalDateTime startTime,
            @RequestParam @DateTimeFormat(pattern = "yyyy-MM-dd HH:mm:ss") LocalDateTime endTime) {
        return Result.success(telemetryService.getByTimeRange(droneId, startTime, endTime));
    }
}
