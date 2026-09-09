package com.coldaviation.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.coldaviation.entity.BatteryStatus;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/**
 * 电池状态数据访问层
 */
@Mapper
public interface BatteryMapper extends BaseMapper<BatteryStatus> {

    /**
     * 查询指定无人机的最新电池状态
     */
    @Select("SELECT * FROM battery_status WHERE drone_id = #{droneId} ORDER BY assess_time DESC LIMIT 1")
    BatteryStatus selectLatestByDroneId(@Param("droneId") Long droneId);

    /**
     * 查询指定无人机的电池健康历史记录（用于衰减曲线）
     */
    @Select("SELECT * FROM battery_status WHERE drone_id = #{droneId} ORDER BY assess_time DESC LIMIT #{limit}")
    List<BatteryStatus> selectHistoryByDroneId(@Param("droneId") Long droneId, @Param("limit") int limit);
}
