package com.coldaviation.service.impl;

import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.coldaviation.entity.FlightPlan;
import com.coldaviation.mapper.FlightPlanMapper;
import com.coldaviation.service.FlightPlanService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.List;

@Slf4j
@Service
public class FlightPlanServiceImpl extends ServiceImpl<FlightPlanMapper, FlightPlan> implements FlightPlanService {

    @Override
    public List<FlightPlan> getByDroneId(Long droneId) {
        return baseMapper.selectByDroneId(droneId);
    }

    @Override
    public List<FlightPlan> getExecutingPlans() {
        return baseMapper.selectExecutingPlans();
    }

    @Override
    public boolean createPlan(FlightPlan plan) {
        plan.setStatus(0); // 草稿状态
        boolean saved = save(plan);
        if (saved) {
            log.info("航线计划已创建: planName={}, droneCode={}", plan.getPlanName(), plan.getDroneCode());
        }
        return saved;
    }

    @Override
    public boolean updatePlanStatus(Long planId, Integer status) {
        LambdaUpdateWrapper<FlightPlan> wrapper = new LambdaUpdateWrapper<>();
        wrapper.eq(FlightPlan::getId, planId).set(FlightPlan::getStatus, status);
        return update(wrapper);
    }
}
