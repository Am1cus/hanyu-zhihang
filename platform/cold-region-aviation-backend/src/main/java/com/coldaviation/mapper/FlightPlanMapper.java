package com.coldaviation.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.coldaviation.entity.FlightPlan;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/**
 * 航线计划数据访问层
 */
@Mapper
public interface FlightPlanMapper extends BaseMapper<FlightPlan> {

    /**
     * 查询指定无人机的航线计划
     */
    @Select("SELECT * FROM flight_plan WHERE drone_id = #{droneId} ORDER BY create_time DESC")
    List<FlightPlan> selectByDroneId(@Param("droneId") Long droneId);

    /**
     * 查询正在执行中的航线
     */
    @Select("SELECT * FROM flight_plan WHERE status = 2")
    List<FlightPlan> selectExecutingPlans();
}
