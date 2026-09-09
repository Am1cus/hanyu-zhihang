package com.coldaviation.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 电池状态实体 - 记录电池健康评估数据
 */
@Data
@TableName("battery_status")
public class BatteryStatus implements Serializable {

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 关联无人机ID */
    private Long droneId;

    /** 无人机编号 */
    private String droneCode;

    /** 电池编号 */
    private String batteryCode;

    /** 电池健康评分 (0-100) */
    private Double healthScore;

    /** 当前电量百分比 (%) */
    private Double currentLevel;

    /** 当前电压 (V) */
    private Double currentVoltage;

    /** 内阻 (mΩ) */
    private Double internalResistance;

    /** 电池温度 (°C) */
    private Double temperature;

    /** 充放电循环次数 */
    private Integer cycleCount;

    /** 标称容量 (mAh) */
    private Integer nominalCapacity;

    /** 当前可用容量 (mAh) */
    private Integer availableCapacity;

    /** AI预测的剩余航程 (km) */
    private Double predictedRange;

    /** AI预测的剩余飞行时间 (min) */
    private Double predictedFlightTime;

    /** 容量衰减率 (%) - 受低温影响 */
    private Double capacityDecayRate;

    /** 评估环境温度 (°C) */
    private Double assessTemperature;

    /** 评估时间 */
    private LocalDateTime assessTime;

    /** 创建时间 */
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createTime;
}
