import request from './request'

export const getModelReport = () => request.get('/dashboard/model-report', { silent: true })
export const getEnergyV3Report = () => request.get('/dashboard/energy-v3-report', { silent: true })

/** 使用训练区间之外的固定样本执行一次真实容量LSTM V1推理 */
export const getLstmCapacityValidation = (caseIndex) =>
  request.get('/demo/lstm-capacity', { params: { caseIndex }, silent: true })
