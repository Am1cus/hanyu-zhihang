package com.coldaviation.controller;

import com.coldaviation.common.Result;
import com.coldaviation.service.AiPredictionService;
import com.coldaviation.service.DroneService;
import com.coldaviation.service.WarningService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.HashMap;
import java.util.Map;

/**
 * 看板数据控制器 - 提供监控大屏所需的聚合数据
 */
@Slf4j
@RestController
@RequestMapping("/api/dashboard")
public class DashboardController {

    @Autowired
    private DroneService droneService;

    @Autowired
    private WarningService warningService;

    @Autowired
    private AiPredictionService aiPredictionService;

    @GetMapping("/model-report")
    public Result<Map<String, Object>> getModelReport() {
        return Result.success(aiPredictionService.getAirSimCapacityReport());
    }

    @GetMapping("/energy-v3-report")
    public Result<Map<String,Object>> getEnergyV3Report() {
        return Result.success(aiPredictionService.getEnergyV3Report());
    }

    /** 获取看板概览数据 */
    @GetMapping("/overview")
    public Result<Map<String, Object>> getOverview() {
        Map<String, Object> overview = new HashMap<>();

        // 无人机总数
        overview.put("totalDrones", droneService.count());
        // 在线无人机数
        overview.put("activeDrones", droneService.getActiveDrones().size());
        // 各状态统计
        overview.put("droneStatusStats", droneService.getStatusStatistics());
        // 未处理预警数
        overview.put("unhandledWarnings", warningService.getUnhandledWarnings().size());
        // 预警类型统计
        overview.put("warningTypeStats", warningService.getTypeStatistics());
        // 预警级别统计
        overview.put("warningLevelStats", warningService.getLevelStatistics());
        // 区分 AI 服务在线状态、容量模型 V1 和飞行时间模型 V2 状态
        Map<String, Object> aiStatus = aiPredictionService.getAiServiceStatus();
        overview.put("aiServiceOnline", aiStatus.get("online"));
        overview.put("aiStatus", aiStatus);

        return Result.success(overview);
    }

    /** 获取在线无人机列表（用于地图展示） */
    @GetMapping("/active-drones")
    public Result<?> getActiveDrones() {
        return Result.success(droneService.getActiveDrones());
    }

    /** 获取最新未处理预警（用于预警弹窗） */
    @GetMapping("/latest-warnings")
    public Result<?> getLatestWarnings() {
        return Result.success(warningService.getUnhandledWarnings());
    }
}
