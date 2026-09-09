import request from './request'

/** 分页查询无人机 */
export const getDroneList = (params) => request.get('/drone/list', { params })

/** 获取在线无人机 */
export const getActiveDrones = () => request.get('/drone/active')

/** 获取无人机详情 */
export const getDroneById = (id) => request.get(`/drone/${id}`)

/** 新增无人机 */
export const addDrone = (data) => request.post('/drone', data)

/** 更新无人机 */
export const updateDrone = (data) => request.put('/drone', data)

/** 删除无人机 */
export const deleteDrone = (id) => request.delete(`/drone/${id}`)

/** 更新状态 */
export const updateDroneStatus = (id, status) => request.put(`/drone/${id}/status/${status}`)

/** 状态统计 */
export const getDroneStatusStats = () => request.get('/drone/statistics/status')
