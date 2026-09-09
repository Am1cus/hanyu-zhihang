import request from './request'

export const getFlightPlans = () => request.get('/flight-plan/list')
export const createFlightPlan = (data) => request.post('/flight-plan', data)
export const updateFlightPlanStatus = (id, status) => request.put(`/flight-plan/${id}/status/${status}`)
