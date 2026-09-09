package com.coldaviation.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.coldaviation.common.Result;
import com.coldaviation.entity.Drone;
import com.coldaviation.service.DroneService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 无人机管理控制器
 */
@Slf4j
@RestController
@RequestMapping("/api/drone")
public class DroneController {

    @Autowired
    private DroneService droneService;

    /** 分页查询无人机列表 */
    @GetMapping("/list")
    public Result<Page<Drone>> list(
            @RequestParam(defaultValue = "1") int pageNum,
            @RequestParam(defaultValue = "10") int pageSize,
            @RequestParam(required = false) String keyword,
            @RequestParam(required = false) Integer status) {
        return Result.success(droneService.pageDrones(pageNum, pageSize, keyword, status));
    }

    /** 获取所有在线无人机 */
    @GetMapping("/active")
    public Result<List<Drone>> getActiveDrones() {
        return Result.success(droneService.getActiveDrones());
    }

    /** 根据ID获取无人机详情 */
    @GetMapping("/{id}")
    public Result<Drone> getById(@PathVariable Long id) {
        return Result.success(droneService.getById(id));
    }

    /** 根据编号获取无人机 */
    @GetMapping("/code/{droneCode}")
    public Result<Drone> getByCode(@PathVariable String droneCode) {
        return Result.success(droneService.getByDroneCode(droneCode));
    }

    /** 新增无人机 */
    @PostMapping
    public Result<Boolean> add(@RequestBody Drone drone) {
        return Result.success(droneService.save(drone));
    }

    /** 更新无人机信息 */
    @PutMapping
    public Result<Boolean> update(@RequestBody Drone drone) {
        return Result.success(droneService.updateById(drone));
    }

    /** 删除无人机 */
    @DeleteMapping("/{id}")
    public Result<Boolean> delete(@PathVariable Long id) {
        return Result.success(droneService.removeById(id));
    }

    /** 更新无人机状态 */
    @PutMapping("/{id}/status/{status}")
    public Result<Boolean> updateStatus(@PathVariable Long id, @PathVariable Integer status) {
        return Result.success(droneService.updateDroneStatus(id, status));
    }

    /** 获取状态统计 */
    @GetMapping("/statistics/status")
    public Result<List<Map<String, Object>>> getStatusStatistics() {
        return Result.success(droneService.getStatusStatistics());
    }
}
