package com.coldaviation.common;

/**
 * 系统常量定义
 */
public class Constants {

    /** 无人机状态 */
    public static final int DRONE_STATUS_OFFLINE = 0;
    public static final int DRONE_STATUS_ONLINE = 1;
    public static final int DRONE_STATUS_FLYING = 2;
    public static final int DRONE_STATUS_WARNING = 3;
    public static final int DRONE_STATUS_EMERGENCY = 4;

    /** 预警级别 */
    public static final int WARNING_LEVEL_NOTICE = 1;    // 注意
    public static final int WARNING_LEVEL_WARNING = 2;   // 警告
    public static final int WARNING_LEVEL_DANGER = 3;    // 危险
    public static final int WARNING_LEVEL_CRITICAL = 4;  // 紧急

    /** 预警类型 */
    public static final String WARNING_TYPE_BATTERY = "BATTERY";       // 电池预警
    public static final String WARNING_TYPE_TEMPERATURE = "TEMPERATURE"; // 温度预警
    public static final String WARNING_TYPE_WIND = "WIND";             // 风速预警
    public static final String WARNING_TYPE_SIGNAL = "SIGNAL";         // 信号预警

    /** 电池健康评分阈值 */
    public static final double BATTERY_HEALTH_GOOD = 80.0;
    public static final double BATTERY_HEALTH_NORMAL = 60.0;
    public static final double BATTERY_HEALTH_WARNING = 40.0;
    public static final double BATTERY_HEALTH_DANGER = 20.0;

    /** 极寒温度阈值 (°C) */
    public static final double TEMP_COLD_THRESHOLD = -15.0;
    public static final double TEMP_EXTREME_COLD_THRESHOLD = -25.0;

    /** Redis Key 前缀 */
    public static final String REDIS_KEY_DRONE_STATUS = "drone:status:";
    public static final String REDIS_KEY_TELEMETRY = "telemetry:realtime:";
    public static final String REDIS_KEY_WARNING = "warning:active:";

    /** WebSocket 端点 */
    public static final String WS_ENDPOINT_TELEMETRY = "/ws/telemetry";

    /** Python AI 推理服务地址 */
    public static final String AI_SERVICE_DEFAULT_URL = "http://localhost:8000";
}
