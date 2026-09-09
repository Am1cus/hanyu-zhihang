package com.coldaviation.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.coldaviation.common.Result;
import com.coldaviation.entity.WarningRecord;
import com.coldaviation.service.WarningService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 预警管理控制器
 */
@Slf4j
@RestController
@RequestMapping("/api/warning")
public class WarningController {

    @Autowired
    private WarningService warningService;

    /** 分页查询预警记录 */
    @GetMapping("/list")
    public Result<Page<WarningRecord>> list(
            @RequestParam(defaultValue = "1") int pageNum,
            @RequestParam(defaultValue = "10") int pageSize,
            @RequestParam(required = false) String warningType,
            @RequestParam(required = false) Integer warningLevel,
            @RequestParam(required = false) Integer handleStatus) {
        return Result.success(warningService.pageWarnings(pageNum, pageSize, warningType, warningLevel, handleStatus));
    }

    /** 获取未处理的预警 */
    @GetMapping("/unhandled")
    public Result<List<WarningRecord>> getUnhandled() {
        return Result.success(warningService.getUnhandledWarnings());
    }

    /** 处理预警 */
    @PutMapping("/handle/{id}")
    public Result<Boolean> handle(
            @PathVariable Long id,
            @RequestParam Integer handleStatus,
            @RequestParam(required = false) String handleResult) {
        return Result.success(warningService.handleWarning(id, handleStatus, handleResult));
    }

    /** 创建预警 */
    @PostMapping
    public Result<Boolean> create(@RequestBody WarningRecord record) {
        return Result.success(warningService.createWarning(record));
    }

    /** 获取指定无人机的最近预警 */
    @GetMapping("/recent/{droneId}")
    public Result<List<WarningRecord>> getRecent(
            @PathVariable Long droneId,
            @RequestParam(defaultValue = "10") int limit) {
        return Result.success(warningService.getRecentByDroneId(droneId, limit));
    }

    /** 按类型统计 */
    @GetMapping("/statistics/type")
    public Result<List<Map<String, Object>>> typeStatistics() {
        return Result.success(warningService.getTypeStatistics());
    }

    /** 按级别统计 */
    @GetMapping("/statistics/level")
    public Result<List<Map<String, Object>>> levelStatistics() {
        return Result.success(warningService.getLevelStatistics());
    }
}
