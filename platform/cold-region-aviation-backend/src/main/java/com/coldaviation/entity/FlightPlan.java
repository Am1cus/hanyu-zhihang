package com.coldaviation.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 航线计划实体
 */
@Data
@TableName("flight_plan")
public class FlightPlan implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 关联无人机ID */
    private Long droneId;

    /** 无人机编号 */
    private String droneCode;

    /** 航线名称 */
    private String planName;

    /** 航线描述 */
    private String description;

    /** 起点纬度 */
    private Double startLatitude;

    /** 起点经度 */
    private Double startLongitude;

    /** 终点纬度 */
    private Double endLatitude;

    /** 终点经度 */
    private Double endLongitude;

    /** 航线路径点 (JSON格式存储) */
    private String waypoints;

    /** 计划飞行高度 (m) */
    private Double planAltitude;

    /** 计划飞行速度 (m/s) */
    private Double planSpeed;

    /** 预计航程 (km) */
    private Double estimatedDistance;

    /** 预计飞行时间 (min) */
    private Double estimatedTime;

    /** 预计能耗 (%) */
    private Double estimatedEnergy;

    /** 规划算法类型: ASTAR/ASTAR_IMPROVED */
    private String algorithmType;

    /** 规划时的环境温度 (°C) */
    private Double planTemperature;

    /** 规划时的风速 (m/s) */
    private Double planWindSpeed;

    /** 状态: 0-草稿 1-已确认 2-执行中 3-已完成 4-已取消 */
    private Integer status;

    /** 创建时间 */
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createTime;

    /** 更新时间 */
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updateTime;
}
