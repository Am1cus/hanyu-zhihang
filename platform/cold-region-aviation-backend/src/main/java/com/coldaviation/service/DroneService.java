package com.coldaviation.service;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.extension.service.IService;
import com.coldaviation.entity.Drone;

import java.util.List;
import java.util.Map;

/**
 * 无人机管理服务接口
 */
public interface DroneService extends IService<Drone> {

    /**
     * 分页查询无人机列表
     */
    Page<Drone> pageDrones(int pageNum, int pageSize, String keyword, Integer status);

    /**
     * 根据编号查询无人机
     */
    Drone getByDroneCode(String droneCode);

    /**
     * 获取所有在线/飞行中的无人机
     */
    List<Drone> getActiveDrones();

    /**
     * 按状态统计无人机数量
     */
    List<Map<String, Object>> getStatusStatistics();

    /**
     * 更新无人机状态
     */
    boolean updateDroneStatus(Long droneId, Integer status);

    /**
     * 更新无人机位置信息
     */
    boolean updateDronePosition(Long droneId, Double latitude, Double longitude, Double altitude);

    /** 使用最新遥测同步演示无人机位置、电量与飞行状态。 */
    boolean updateDroneTelemetry(Long droneId, Double latitude, Double longitude,
                                 Double altitude, Double batteryLevel);
}
