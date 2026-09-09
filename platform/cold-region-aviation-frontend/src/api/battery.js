import request from './request'

/** 获取最新电池状态 */
export const getLatestBattery = (droneId) => request.get(`/battery/latest/${droneId}`)

/** 获取健康历史 */
export const getBatteryHistory = (droneId, limit = 50) =>
  request.get(`/battery/history/${droneId}`, { params: { limit } })

/** 触发AI预测 */
export const predictPowerDecay = (params) => request.post('/battery/predict', null, { params })

/** 保存电池评估 */
export const saveBatteryStatus = (data) => request.post('/battery', data)

/** 检查AI服务 */
export const checkAiStatus = () => request.get('/battery/ai-status')
