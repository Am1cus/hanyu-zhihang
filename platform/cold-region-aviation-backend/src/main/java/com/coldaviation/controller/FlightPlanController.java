package com.coldaviation.controller;

import com.coldaviation.common.Result;
import com.coldaviation.entity.FlightPlan;
import com.coldaviation.service.AiPredictionService;
import com.coldaviation.service.FlightPlanService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 航线规划控制器
 */
@Slf4j
@RestController
@RequestMapping("/api/flight-plan")
public class FlightPlanController {

    @Autowired
    private FlightPlanService flightPlanService;

    @Autowired
    private AiPredictionService aiPredictionService;

    /** 查询全部航线，供演示看板使用。 */
    @GetMapping("/list")
    public Result<List<FlightPlan>> list() {
        return Result.success(flightPlanService.list());
    }

    /** 查询指定无人机的航线 */
    @GetMapping("/drone/{droneId}")
    public Result<List<FlightPlan>> getByDroneId(@PathVariable Long droneId) {
        return Result.success(flightPlanService.getByDroneId(droneId));
    }

    /** 查询执行中的航线 */
    @GetMapping("/executing")
    public Result<List<FlightPlan>> getExecuting() {
        return Result.success(flightPlanService.getExecutingPlans());
    }

    /** 获取航线详情 */
    @GetMapping("/{id}")
    public Result<FlightPlan> getById(@PathVariable Long id) {
        return Result.success(flightPlanService.getById(id));
    }

    /** 创建航线计划 */
    @PostMapping
    public Result<Boolean> create(@RequestBody FlightPlan plan) {
        return Result.success(flightPlanService.createPlan(plan));
    }

    /** 更新航线计划 */
    @PutMapping
    public Result<Boolean> update(@RequestBody FlightPlan plan) {
        return Result.success(flightPlanService.updateById(plan));
    }

    /** 更新航线状态 */
    @PutMapping("/{id}/status/{status}")
    public Result<Boolean> updateStatus(@PathVariable Long id, @PathVariable Integer status) {
        return Result.success(flightPlanService.updatePlanStatus(id, status));
    }

    /** 删除航线 */
    @DeleteMapping("/{id}")
    public Result<Boolean> delete(@PathVariable Long id) {
        return Result.success(flightPlanService.removeById(id));
    }

    /** 调用AI进行智能路径规划 */
    @PostMapping("/ai-plan")
    public Result<Map<String, Object>> aiPlanRoute(
            @RequestParam Double startLat, @RequestParam Double startLon,
            @RequestParam Double endLat, @RequestParam Double endLon,
            @RequestParam Double temperature, @RequestParam Double windSpeed,
            @RequestParam Double windDirection, @RequestParam Double batteryLevel) {
        Map<String, Object> result = aiPredictionService.planRoute(
                startLat, startLon, endLat, endLon, temperature, windSpeed, windDirection, batteryLevel);
        return Result.success(result);
    }
}
