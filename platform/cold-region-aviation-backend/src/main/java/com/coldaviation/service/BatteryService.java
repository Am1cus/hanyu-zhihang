package com.coldaviation.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.coldaviation.entity.BatteryStatus;

import java.util.List;

/**
 * 电池健康评估服务接口
 */
public interface BatteryService extends IService<BatteryStatus> {

    /**
     * 获取指定无人机的最新电池状态
     */
    BatteryStatus getLatestByDroneId(Long droneId);

    /**
     * 获取电池历史健康记录（衰减曲线数据）
     */
    List<BatteryStatus> getHealthHistory(Long droneId, int limit);

    /**
     * 保存电池评估结果（来自AI预测）
     */
    boolean saveBatteryAssessment(BatteryStatus batteryStatus);
}
