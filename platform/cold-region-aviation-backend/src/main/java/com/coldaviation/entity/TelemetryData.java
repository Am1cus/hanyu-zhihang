package com.coldaviation.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import com.fasterxml.jackson.annotation.JsonInclude;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 遥测数据实体 - 记录无人机实时飞行数据
 */
@Data
@TableName("telemetry_data")
public class TelemetryData implements Serializable {

    private String runId;
    private String flightId;
    private Integer sampleSeq;
    /** Original flight-relative time after 1 Hz aggregation, not replay wall time. */
    private Double sourceTimeS;
    private String payloadSha256;

    // Omit absent new fields so legacy payload fingerprints remain reproducible.
    @JsonInclude(JsonInclude.Include.NON_NULL)
    private Double velocityX;
    @JsonInclude(JsonInclude.Include.NON_NULL)
    private Double velocityY;
    @JsonInclude(JsonInclude.Include.NON_NULL)
    private Double velocityZ;
    @JsonInclude(JsonInclude.Include.NON_NULL)
    private Double windX;
    @JsonInclude(JsonInclude.Include.NON_NULL)
    private Double windY;
    @JsonInclude(JsonInclude.Include.NON_NULL)
    private Double windZ;

    @TableId(type = IdType.AUTO)
    private Long id;

    /** 关联无人机ID */
    private Long droneId;

    /** 无人机编号 */
    private String droneCode;

    /** 纬度 */
    private Double latitude;

    /** 经度 */
    private Double longitude;

    /** 飞行高度 (m) */
    private Double altitude;

    /** 飞行速度 (m/s) */
    private Double speed;

    /** 航向角 (°) */
    private Double heading;

    /** 电池电压 (V) */
    private Double voltage;

    /** 电池电流 (A) */
    private Double current;

    /** 电池电量百分比 (%) */
    private Double batteryLevel;

    /** AirSim仿真的当前剩余容量 (Ah)，用于预测结果回测 */
    private Double remainingCapacityAh;

    /** 电池温度 (°C) */
    private Double batteryTemperature;

    /** 环境温度 (°C) */
    private Double envTemperature;

    /** 风速 (m/s) */
    private Double windSpeed;

    /** 风向 (°) */
    private Double windDirection;

    /** 湿度 (%) */
    private Double humidity;

    /** 信号强度 (dBm) */
    private Integer signalStrength;

    /** 数据采集时间 */
    private LocalDateTime collectTime;

    /** 创建时间 */
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createTime;
}
