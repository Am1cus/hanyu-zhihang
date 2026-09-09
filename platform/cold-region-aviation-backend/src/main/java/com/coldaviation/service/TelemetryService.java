package com.coldaviation.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.coldaviation.entity.TelemetryData;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 遥测数据服务接口
 */
public interface TelemetryService extends IService<TelemetryData> {

    /**
     * 保存遥测数据并缓存至Redis
     */
    boolean saveTelemetry(TelemetryData data);

    /**
     * 获取指定无人机的最新遥测数据
     */
    TelemetryData getLatestByDroneId(Long droneId);

    /**
     * 查询指定时间范围内的遥测数据
     */
    List<TelemetryData> getByTimeRange(Long droneId, LocalDateTime startTime, LocalDateTime endTime);

    /**
     * 从Redis获取实时遥测数据
     */
    TelemetryData getRealtimeFromCache(Long droneId);

    /**
     * 清空演示回放使用的内存窗口、预警冷却和遥测缓存。
     */
    void resetRuntimeState();
}
