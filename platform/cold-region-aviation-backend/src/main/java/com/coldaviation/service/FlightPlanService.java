package com.coldaviation.service;

import com.baomidou.mybatisplus.extension.service.IService;
import com.coldaviation.entity.FlightPlan;

import java.util.List;

/**
 * 航线规划服务接口
 */
public interface FlightPlanService extends IService<FlightPlan> {

    /**
     * 查询指定无人机的航线计划
     */
    List<FlightPlan> getByDroneId(Long droneId);

    /**
     * 查询正在执行中的航线
     */
    List<FlightPlan> getExecutingPlans();

    /**
     * 创建航线计划
     */
    boolean createPlan(FlightPlan plan);

    /**
     * 更新航线状态
     */
    boolean updatePlanStatus(Long planId, Integer status);
}
