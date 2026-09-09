package com.coldaviation.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.coldaviation.entity.TelemetryData;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 遥测数据访问层
 */
@Mapper
public interface TelemetryMapper extends BaseMapper<TelemetryData> {

    /**
     * 查询指定无人机的最新遥测数据
     */
    @Select("SELECT * FROM telemetry_data WHERE drone_id = #{droneId} ORDER BY collect_time DESC LIMIT 1")
    TelemetryData selectLatestByDroneId(@Param("droneId") Long droneId);

    /**
     * 查询指定时间范围内的遥测数据
     */
    @Select("SELECT * FROM telemetry_data WHERE drone_id = #{droneId} AND collect_time BETWEEN #{startTime} AND #{endTime} ORDER BY collect_time ASC")
    List<TelemetryData> selectByTimeRange(@Param("droneId") Long droneId,
                                           @Param("startTime") LocalDateTime startTime,
                                           @Param("endTime") LocalDateTime endTime);
}
