package com.coldaviation.service;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.extension.service.IService;
import com.coldaviation.entity.WarningRecord;

import java.util.List;
import java.util.Map;

/**
 * 预警管理服务接口
 */
public interface WarningService extends IService<WarningRecord> {

    /**
     * 分页查询预警记录
     */
    Page<WarningRecord> pageWarnings(int pageNum, int pageSize, String warningType, Integer warningLevel, Integer handleStatus);

    /**
     * 获取未处理的预警
     */
    List<WarningRecord> getUnhandledWarnings();

    /**
     * 处理预警
     */
    boolean handleWarning(Long warningId, Integer handleStatus, String handleResult);

    /**
     * 按类型统计
     */
    List<Map<String, Object>> getTypeStatistics();

    /**
     * 按级别统计
     */
    List<Map<String, Object>> getLevelStatistics();

    /**
     * 创建预警记录
     */
    boolean createWarning(WarningRecord record);

    /**
     * 获取指定无人机最近预警
     */
    List<WarningRecord> getRecentByDroneId(Long droneId, int limit);
}
