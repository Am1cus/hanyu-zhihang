import request from './request'

/** 上报遥测数据 */
export const reportTelemetry = (data) => request.post('/telemetry', data)

/** 获取最新遥测 */
export const getLatestTelemetry = (droneId) => request.get(`/telemetry/latest/${droneId}`)

/** 获取实时遥测(Redis) */
export const getRealtimeTelemetry = (droneId) => request.get(`/telemetry/realtime/${droneId}`)

/** 查询历史遥测 */
export const getTelemetryHistory = (droneId, startTime, endTime) =>
  request.get(`/telemetry/history/${droneId}`, { params: { startTime, endTime } })
