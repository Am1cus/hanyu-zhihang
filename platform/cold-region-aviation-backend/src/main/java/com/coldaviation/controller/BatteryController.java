package com.coldaviation.controller;

import com.coldaviation.common.Result;
import com.coldaviation.entity.BatteryStatus;
import com.coldaviation.service.AiPredictionService;
import com.coldaviation.service.BatteryService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 电池健康管理控制器
 */
@Slf4j
@RestController
@RequestMapping("/api/battery")
public class BatteryController {

    @Autowired
    private BatteryService batteryService;

    @Autowired
    private AiPredictionService aiPredictionService;

    /** 获取指定无人机的最新电池状态 */
    @GetMapping("/latest/{droneId}")
    public Result<BatteryStatus> getLatest(@PathVariable Long droneId) {
        return Result.success(batteryService.getLatestByDroneId(droneId));
    }

    /** 获取电池健康历史（衰减曲线数据） */
    @GetMapping("/history/{droneId}")
    public Result<List<BatteryStatus>> getHistory(
            @PathVariable Long droneId,
            @RequestParam(defaultValue = "50") int limit) {
        return Result.success(batteryService.getHealthHistory(droneId, limit));
    }

    /** 手动触发AI动力衰减预测 */
    @PostMapping("/predict")
    public Result<Map<String, Object>> predict(
            @RequestParam Long droneId,
            @RequestParam Double voltage,
            @RequestParam Double current,
            @RequestParam Double temperature,
            @RequestParam Double windSpeed,
            @RequestParam Double batteryLevel) {
        Map<String, Object> prediction = aiPredictionService.predictPowerDecay(
                droneId, voltage, current, temperature, windSpeed, batteryLevel);
        return Result.success(prediction);
    }

    /** 保存电池评估结果 */
    @PostMapping
    public Result<Boolean> saveBatteryStatus(@RequestBody BatteryStatus batteryStatus) {
        return Result.success(batteryService.saveBatteryAssessment(batteryStatus));
    }

    /** 检查AI服务状态 */
    @GetMapping("/ai-status")
    public Result<Boolean> checkAiService() {
        return Result.success(aiPredictionService.isAiServiceOnline());
    }
}
