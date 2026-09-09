package com.coldaviation.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.coldaviation.entity.Drone;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

import java.util.List;

/**
 * 无人机数据访问层
 */
@Mapper
public interface DroneMapper extends BaseMapper<Drone> {

    /**
     * 按状态统计无人机数量
     */
    @Select("SELECT status, COUNT(*) as count FROM drone WHERE deleted = 0 GROUP BY status")
    List<java.util.Map<String, Object>> countByStatus();

    /**
     * 查询所有在线/飞行中的无人机
     */
    @Select("SELECT * FROM drone WHERE deleted = 0 AND status IN (1, 2, 3)")
    List<Drone> selectActiveDrones();
}
