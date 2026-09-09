package com.coldaviation.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.coldaviation.entity.Drone;
import com.coldaviation.mapper.DroneMapper;
import com.coldaviation.service.DroneService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

import java.util.List;
import java.util.Map;

@Slf4j
@Service
public class DroneServiceImpl extends ServiceImpl<DroneMapper, Drone> implements DroneService {

    @Override
    public Page<Drone> pageDrones(int pageNum, int pageSize, String keyword, Integer status) {
        LambdaQueryWrapper<Drone> wrapper = new LambdaQueryWrapper<>();
        if (StringUtils.hasText(keyword)) {
            wrapper.and(w -> w.like(Drone::getDroneName, keyword)
                    .or().like(Drone::getDroneCode, keyword)
                    .or().like(Drone::getModel, keyword));
        }
        if (status != null) {
            wrapper.eq(Drone::getStatus, status);
        }
        wrapper.orderByDesc(Drone::getUpdateTime);
        return page(new Page<>(pageNum, pageSize), wrapper);
    }

    @Override
    public Drone getByDroneCode(String droneCode) {
        return getOne(new LambdaQueryWrapper<Drone>().eq(Drone::getDroneCode, droneCode));
    }

    @Override
    public List<Drone> getActiveDrones() {
        return baseMapper.selectActiveDrones();
    }

    @Override
    public List<Map<String, Object>> getStatusStatistics() {
        return baseMapper.countByStatus();
    }

    @Override
    public boolean updateDroneStatus(Long droneId, Integer status) {
        LambdaUpdateWrapper<Drone> wrapper = new LambdaUpdateWrapper<>();
        wrapper.eq(Drone::getId, droneId).set(Drone::getStatus, status);
        return update(wrapper);
    }

    @Override
    public boolean updateDronePosition(Long droneId, Double latitude, Double longitude, Double altitude) {
        LambdaUpdateWrapper<Drone> wrapper = new LambdaUpdateWrapper<>();
        wrapper.eq(Drone::getId, droneId)
                .set(Drone::getLatitude, latitude)
                .set(Drone::getLongitude, longitude)
                .set(Drone::getAltitude, altitude);
        return update(wrapper);
    }

    @Override
    public boolean updateDroneTelemetry(Long droneId, Double latitude, Double longitude,
                                        Double altitude, Double batteryLevel) {
        LambdaUpdateWrapper<Drone> wrapper = new LambdaUpdateWrapper<>();
        wrapper.eq(Drone::getId, droneId)
                .set(Drone::getStatus, 2)
                .set(Drone::getLatitude, latitude)
                .set(Drone::getLongitude, longitude)
                .set(Drone::getAltitude, altitude)
                .set(Drone::getBatteryLevel, batteryLevel)
                .set(Drone::getUpdateTime, java.time.LocalDateTime.now());
        return update(wrapper);
    }
}
