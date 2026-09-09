package com.coldaviation.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.coldaviation.entity.WarningRecord;
import com.coldaviation.mapper.WarningMapper;
import com.coldaviation.service.WarningService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

@Slf4j
@Service
public class WarningServiceImpl extends ServiceImpl<WarningMapper, WarningRecord> implements WarningService {

    @Override
    public Page<WarningRecord> pageWarnings(int pageNum, int pageSize, String warningType,
                                             Integer warningLevel, Integer handleStatus) {
        LambdaQueryWrapper<WarningRecord> wrapper = new LambdaQueryWrapper<>();
        if (StringUtils.hasText(warningType)) {
            wrapper.eq(WarningRecord::getWarningType, warningType);
        }
        if (warningLevel != null) {
            wrapper.eq(WarningRecord::getWarningLevel, warningLevel);
        }
        if (handleStatus != null) {
            wrapper.eq(WarningRecord::getHandleStatus, handleStatus);
        }
        wrapper.orderByDesc(WarningRecord::getWarningTime);
        return page(new Page<>(pageNum, pageSize), wrapper);
    }

    @Override
    public List<WarningRecord> getUnhandledWarnings() {
        return baseMapper.selectUnhandled();
    }

    @Override
    public boolean handleWarning(Long warningId, Integer handleStatus, String handleResult) {
        LambdaUpdateWrapper<WarningRecord> wrapper = new LambdaUpdateWrapper<>();
        wrapper.eq(WarningRecord::getId, warningId)
                .set(WarningRecord::getHandleStatus, handleStatus)
                .set(WarningRecord::getHandleResult, handleResult)
                .set(WarningRecord::getHandleTime, LocalDateTime.now());
        return update(wrapper);
    }

    @Override
    public List<Map<String, Object>> getTypeStatistics() {
        return baseMapper.countByType();
    }

    @Override
    public List<Map<String, Object>> getLevelStatistics() {
        return baseMapper.countByLevel();
    }

    @Override
    public boolean createWarning(WarningRecord record) {
        record.setWarningTime(LocalDateTime.now());
        record.setHandleStatus(0);
        boolean saved = save(record);
        if (saved) {
            log.warn("新预警已创建: droneCode={}, type={}, level={}",
                    record.getDroneCode(), record.getWarningType(), record.getWarningLevel());
        }
        return saved;
    }

    @Override
    public List<WarningRecord> getRecentByDroneId(Long droneId, int limit) {
        return baseMapper.selectRecentByDroneId(droneId, limit);
    }
}
