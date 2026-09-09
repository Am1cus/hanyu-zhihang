import request from './request'

/** 分页查询预警 */
export const getWarningList = (params, config = {}) => request.get('/warning/list', { ...config, params })

/** 获取未处理预警 */
export const getUnhandledWarnings = () => request.get('/warning/unhandled')

/** 处理预警 */
export const handleWarning = (id, handleStatus, handleResult) =>
  request.put(`/warning/handle/${id}`, null, { params: { handleStatus, handleResult } })

/** 创建预警 */
export const createWarning = (data) => request.post('/warning', data)

/** 最近预警 */
export const getRecentWarnings = (droneId, limit = 10) =>
  request.get(`/warning/recent/${droneId}`, { params: { limit } })

/** 类型统计 */
export const getWarningTypeStats = () => request.get('/warning/statistics/type')

/** 级别统计 */
export const getWarningLevelStats = () => request.get('/warning/statistics/level')

/** 看板概览 */
export const getDashboardOverview = (config = {}) => request.get('/dashboard/overview', config)

/** 看板在线无人机 */
export const getDashboardActiveDrones = () => request.get('/dashboard/active-drones')

/** 看板最新预警 */
export const getDashboardLatestWarnings = () => request.get('/dashboard/latest-warnings')
