package com.coldaviation.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 无人机实体
 */
@Data
@TableName("drone")
public class Drone implements Serializable {

    /** 主键ID */
    @TableId(type = IdType.AUTO)
    private Long id;

    /** 无人机编号（唯一标识） */
    private String droneCode;

    /** 无人机名称 */
    private String droneName;

    /** 无人机型号 */
    private String model;

    /** 制造商 */
    private String manufacturer;

    /** 最大载荷 (kg) */
    private Double maxPayload;

    /** 最大航程 (km) */
    private Double maxRange;

    /** 最大飞行速度 (m/s) */
    private Double maxSpeed;

    /** 当前状态: 0-离线 1-在线 2-飞行中 3-告警 4-紧急 */
    private Integer status;

    /** 当前纬度 */
    private Double latitude;

    /** 当前经度 */
    private Double longitude;

    /** 当前高度 (m) */
    private Double altitude;

    /** 当前电池电量 (%) */
    private Double batteryLevel;

    /** 备注信息 */
    private String remark;

    /** 创建时间 */
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createTime;

    /** 更新时间 */
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updateTime;

    /** 逻辑删除标记 */
    @TableLogic
    private Integer deleted;
}
