package com.coldaviation.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.coldaviation.entity.WarningRecord;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;
import java.util.Map;

/**
 * 预警记录数据访问层
 */
@Mapper
public interface WarningMapper extends BaseMapper<WarningRecord> {

    /**
     * 查询未处理的预警记录
     */
    @Select("SELECT * FROM warning_record WHERE handle_status = 0 ORDER BY warning_time DESC")
    List<WarningRecord> selectUnhandled();

    /**
     * 按类型统计预警数量
     */
    @Select("SELECT warning_type, COUNT(*) as count FROM warning_record GROUP BY warning_type")
    List<Map<String, Object>> countByType();

    /**
     * 按级别统计预警数量
     */
    @Select("SELECT warning_level, COUNT(*) as count FROM warning_record GROUP BY warning_level")
    List<Map<String, Object>> countByLevel();

    /**
     * 查询指定无人机最近的预警记录
     */
    @Select("SELECT * FROM warning_record WHERE drone_id = #{droneId} ORDER BY warning_time DESC LIMIT #{limit}")
    List<WarningRecord> selectRecentByDroneId(@Param("droneId") Long droneId, @Param("limit") int limit);
}
