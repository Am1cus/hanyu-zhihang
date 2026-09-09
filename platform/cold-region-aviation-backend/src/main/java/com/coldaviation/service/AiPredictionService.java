package com.coldaviation.service;

import com.coldaviation.entity.TelemetryData;

import java.util.List;
import java.util.Map;

/**
 * AI预测服务接口 - 对接 Python AI 推理模块
 */
public interface AiPredictionService {

    Map<String, Object> predictCapacityRequest(Map<String, Object> request);

    Map<String, Object> getAirSimCapacityReport();
    Map<String, Object> getEnergyV3Report();

    /**
     * 调用 Python AI 服务进行动力衰减预测
     * @param droneId 无人机ID
     * @param voltage 当前电压
     * @param current 当前电流
     * @param temperature 环境温度
     * @param windSpeed 风速
     * @param batteryLevel 当前电量
     * @return 预测结果 (predictedRange, predictedFlightTime, capacityDecayRate, healthScore)
     */
    Map<String, Object> predictPowerDecay(Long droneId, Double voltage, Double current,
                                           Double temperature, Double windSpeed, Double batteryLevel);

    /**
     * 使用最近30秒遥测预测剩余可飞时间。
     */
    Map<String, Object> predictFlightTime(Long droneId, List<TelemetryData> samples);

    /**
     * 使用最近30秒AirSim遥测预测10秒后的剩余容量Ah。
     */
    Map<String, Object> predictAirSimCapacity(Long droneId, List<TelemetryData> samples);

    /**
     * 对训练区间之外的固定样本执行一次容量LSTM V1推理，用于演示模型效果。
     */
    Map<String, Object> predictCapacityValidationCase(int caseIndex);

    /**
     * 调用 Python AI 服务进行路径规划
     * @param startLat 起点纬度
     * @param startLon 起点经度
     * @param endLat 终点纬度
     * @param endLon 终点经度
     * @param temperature 环境温度
     * @param windSpeed 风速
     * @param windDirection 风向
     * @param batteryLevel 剩余电量
     * @return 路径规划结果 (waypoints, estimatedDistance, estimatedTime, estimatedEnergy)
     */
    Map<String, Object> planRoute(Double startLat, Double startLon, Double endLat, Double endLon,
                                   Double temperature, Double windSpeed, Double windDirection,
                                   Double batteryLevel);

    /**
     * 获取 Python AI 服务及各模型的详细状态。
     */
    Map<String, Object> getAiServiceStatus();

    /**
     * 检查 Python AI 服务是否在线
     */
    boolean isAiServiceOnline();
}
