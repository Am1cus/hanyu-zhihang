package com.coldaviation.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 预警记录实体
 */
@Data
@TableName("warning_record")
public class WarningRecord implements Serializable {

    private String runId;
    private String flightId;

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 关联无人机ID */
    private Long droneId;

    /** 无人机编号 */
    private String droneCode;

    /** 预警类型: BATTERY/TEMPERATURE/WIND/SIGNAL */
    private String warningType;

    /** 预警级别: 1-注意 2-警告 3-危险 4-紧急 */
    private Integer warningLevel;

    /** 预警标题 */
    private String title;

    /** 预警详细信息 */
    private String message;

    /** 触发预警时的环境温度 (°C) */
    private Double triggerTemperature;

    /** 触发预警时的电池电量 (%) */
    private Double triggerBatteryLevel;

    /** 触发预警时的风速 (m/s) */
    private Double triggerWindSpeed;

    /** 触发预警时的纬度 */
    private Double triggerLatitude;

    /** 触发预警时的经度 */
    private Double triggerLongitude;

    /** 处理状态: 0-未处理 1-已处理 2-已忽略 */
    private Integer handleStatus;

    /** 处理结果描述 */
    private String handleResult;

    /** 处理时间 */
    private LocalDateTime handleTime;

    /** 预警触发时间 */
    private LocalDateTime warningTime;

    /** 创建时间 */
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createTime;
}
