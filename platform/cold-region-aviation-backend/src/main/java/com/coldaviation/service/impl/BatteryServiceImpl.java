package com.coldaviation.service.impl;

import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.coldaviation.entity.BatteryStatus;
import com.coldaviation.mapper.BatteryMapper;
import com.coldaviation.service.BatteryService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.List;

@Slf4j
@Service
public class BatteryServiceImpl extends ServiceImpl<BatteryMapper, BatteryStatus> implements BatteryService {

    @Override
    public BatteryStatus getLatestByDroneId(Long droneId) {
        return baseMapper.selectLatestByDroneId(droneId);
    }

    @Override
    public List<BatteryStatus> getHealthHistory(Long droneId, int limit) {
        return baseMapper.selectHistoryByDroneId(droneId, limit);
    }

    @Override
    public boolean saveBatteryAssessment(BatteryStatus batteryStatus) {
        boolean saved = save(batteryStatus);
        if (saved) {
            log.info("电池评估结果已保存: droneId={}, healthScore={}, predictedRange={}",
                    batteryStatus.getDroneId(),
                    batteryStatus.getHealthScore(),
                    batteryStatus.getPredictedRange());
        }
        return saved;
    }
}
