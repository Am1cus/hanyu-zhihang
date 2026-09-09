package com.coldaviation.service.impl;

import com.coldaviation.common.Constants;
import com.coldaviation.entity.TelemetryData;
import com.coldaviation.service.AiPredictionService;
import com.coldaviation.service.EnergyV3Contract;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * AI预测服务实现 - 通过HTTP调用Python FastAPI AI推理服务
 */
@Slf4j
@Service
public class AiPredictionServiceImpl implements AiPredictionService {

    @Value("${ai.service.url:" + Constants.AI_SERVICE_DEFAULT_URL + "}")
    private String aiServiceUrl;

    private final RestTemplate restTemplate;

    public AiPredictionServiceImpl() {
        var factory = new org.springframework.http.client.SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(1000);
        factory.setReadTimeout(1500);
        restTemplate = new RestTemplate(factory);
    }

    @Override
    public Map<String, Object> getAirSimCapacityReport() {
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> report = restTemplate.getForObject(
                    aiServiceUrl + "/api/models/airsim-capacity/report", Map.class);
            return report != null ? report : Map.of("unavailable", true);
        } catch (Exception e) {
            return Map.of("unavailable", true, "reason", "ai_service_unavailable");
        }
    }

    @Override
    public Map<String,Object> getEnergyV3Report() {
        try {
            Map<String,Object> report=restTemplate.getForObject(aiServiceUrl+"/api/models/energy-v3/report",Map.class);
            return report!=null ? report : Map.of("unavailable",true);
        } catch(Exception e) { return Map.of("unavailable",true,"reason","ai_service_unavailable"); }
    }

    @Override
    public Map<String, Object> predictPowerDecay(Long droneId, Double voltage, Double current,
                                                  Double temperature, Double windSpeed, Double batteryLevel) {
        return unavailable("single_sample_prediction_deprecated: 请通过遥测流提供30秒窗口");
    }

    @Override
    public Map<String, Object> predictFlightTime(Long droneId, List<TelemetryData> samples) {
        if (samples == null || samples.size() != 30) {
            return unavailable("insufficient_samples: 需要最近30条1Hz遥测");
        }
        TelemetryData first = samples.get(0);
        List<Map<String, Object>> apiSamples = new ArrayList<>();
        for (int index = 0; index < samples.size(); index++) {
            TelemetryData sample = samples.get(index);
            if (!isComplete(sample)) {
                return unavailable("incomplete_telemetry: 温度、风速、电压、电流、电量、速度和高度均为必填");
            }
            double timestampSeconds = index;
            if (first.getCollectTime() != null && sample.getCollectTime() != null) {
                timestampSeconds = Math.max(0, Duration.between(first.getCollectTime(), sample.getCollectTime()).toMillis() / 1000.0);
            }
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("timestamp_s", timestampSeconds);
            item.put("env_temperature_C", sample.getEnvTemperature());
            item.put("wind_speed_ms", sample.getWindSpeed());
            item.put("voltage_V", sample.getVoltage());
            item.put("current_A", sample.getCurrent());
            item.put("battery_level_pct", sample.getBatteryLevel());
            item.put("speed_ms", sample.getSpeed());
            item.put("altitude_m", sample.getAltitude());
            item.put("remaining_capacity_Ah", sample.getRemainingCapacityAh());
            apiSamples.add(item);
        }

        try {
            Map<String, Object> request = new LinkedHashMap<>();
            request.put("drone_id", droneId);
            request.put("samples", apiSamples);
            @SuppressWarnings("unchecked")
            ResponseEntity<Map> response = restTemplate.postForEntity(
                    aiServiceUrl + "/api/predict/flight-time", request, Map.class);
            Map<String, Object> body = response.getBody();
            return body != null ? body : unavailable("empty_ai_response");
        } catch (Exception e) {
            log.warn("飞行时间AI服务不可用: {}", e.getMessage());
            return unavailable("ai_service_unavailable: " + e.getMessage());
        }
    }

    @Override
    public Map<String, Object> predictAirSimCapacity(Long droneId, List<TelemetryData> samples) {
        if (samples == null || samples.size() != 30)
            return capacityUnavailable("insufficient_samples: 需要最近30条1Hz遥测");
        for (TelemetryData sample : samples) {
            String reason = com.coldaviation.service.TelemetryQuality.sampleReason(sample);
            if (reason != null) return capacityUnavailable(reason);
        }
        return predictCapacityRequest(com.coldaviation.service.TelemetryQuality.request(droneId, samples));
    }

    @Override
    public Map<String, Object> predictCapacityRequest(Map<String, Object> request) {
        boolean energyV3=request.containsKey("sampling_contract");
        long started=System.nanoTime();
        try {
            @SuppressWarnings("unchecked")
            ResponseEntity<Map> response = restTemplate.postForEntity(
                    aiServiceUrl + (energyV3 ? "/api/predict/energy-v3" : "/api/predict/airsim-capacity"), request, Map.class);
            Map<String, Object> body = response.getBody();
            if(body!=null) body.put("ai_http_roundtrip_ms",(System.nanoTime()-started)/1000000.0);
            return body != null ? body : energyV3 ? EnergyV3Contract.unavailable("empty_ai_response") : capacityUnavailable("empty_ai_response");
        } catch (Exception e) {
            log.warn("AirSim容量AI服务不可用: {}", e.getMessage());
            return energyV3 ? EnergyV3Contract.unavailable("ai_service_unavailable") : capacityUnavailable("ai_service_unavailable");
        }
    }

    @Override
    public Map<String, Object> predictCapacityValidationCase(int caseIndex) {
        try {
            String url = aiServiceUrl + "/api/demo/capacity-validation/" + caseIndex;
            @SuppressWarnings("unchecked")
            ResponseEntity<Map> response = restTemplate.getForEntity(url, Map.class);
            Map<String, Object> body = response.getBody();
            return body != null ? body : capacityV1Unavailable("empty_ai_response");
        } catch (Exception e) {
            log.warn("容量LSTM演示推理不可用: {}", e.getMessage());
            return capacityV1Unavailable("ai_service_unavailable: " + e.getMessage());
        }
    }

    @Override
    public Map<String, Object> planRoute(Double startLat, Double startLon, Double endLat, Double endLon,
                                          Double temperature, Double windSpeed, Double windDirection,
                                          Double batteryLevel) {
        try {
            String url = aiServiceUrl + "/api/predict/route-plan";

            Map<String, Object> request = new LinkedHashMap<>();
            request.put("start_lat", startLat);
            request.put("start_lon", startLon);
            request.put("end_lat", endLat);
            request.put("end_lon", endLon);
            request.put("temperature", temperature);
            request.put("wind_speed", windSpeed);
            request.put("wind_direction", windDirection);
            request.put("battery_level", batteryLevel);

            log.info("调用AI路径规划接口: ({},{}) -> ({},{}), temp={}°C",
                    startLat, startLon, endLat, endLon, temperature);

            @SuppressWarnings("unchecked")
            ResponseEntity<Map> response = restTemplate.postForEntity(url, request, Map.class);
            return response.getBody();

        } catch (Exception e) {
            log.error("调用AI路径规划接口失败: {}", e.getMessage());
            Map<String, Object> defaultResult = new LinkedHashMap<>();
            defaultResult.put("waypoints", "[]");
            defaultResult.put("error", "AI服务不可用: " + e.getMessage());
            return defaultResult;
        }
    }

    private boolean isComplete(TelemetryData sample) {
        return sample.getEnvTemperature() != null
                && sample.getWindSpeed() != null
                && sample.getVoltage() != null
                && sample.getCurrent() != null
                && sample.getBatteryLevel() != null
                && sample.getSpeed() != null
                && sample.getAltitude() != null;
    }

    private Map<String, Object> unavailable(String reason) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("valid", false);
        result.put("remaining_flight_time_s", null);
        result.put("model_version", "flight_time_lstm_v2");
        result.put("reason", reason);
        result.put("validated_on_real_data", false);
        return result;
    }

    private Map<String, Object> capacityUnavailable(String reason) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("valid", false);
        result.put("predicted_capacity_Ah", null);
        result.put("predicted_consumption_Ah", null);
        result.put("forecast_horizon_s", 10);
        result.put("model_version", "airsim_capacity_lstm_v2");
        result.put("reason", reason);
        result.put("data_source", "AirSim simulation");
        result.put("validated_on_real_data", false);
        return result;
    }

    private Map<String, Object> capacityV1Unavailable(String reason) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("valid", false);
        result.put("predicted_capacity_Ah", null);
        result.put("model_version", "multi_lstm_quantized_v1");
        result.put("reason", reason);
        return result;
    }

    @Override
    public Map<String, Object> getAiServiceStatus() {
        Map<String, Object> status = new LinkedHashMap<>();
        status.put("online", false);
        status.put("capacityModelLoaded", false);
        status.put("capacityModelVersion", null);
        status.put("flightTimeModelAvailable", false);
        status.put("flightTimeModelVersion", "flight_time_lstm_v2");
        status.put("airsimCapacityModelAvailable", false);
        status.put("airsimCapacityModelVersion", "airsim_capacity_lstm_v2");
        status.put("airsimCapacityTestMapePct", null);
        status.put("airsimCapacityForecastHorizonS", 10);
        status.put("quantizationEngine", null);
        status.put("energyV3Available",false);

        try {
            String url = aiServiceUrl + "/health";
            @SuppressWarnings("unchecked")
            ResponseEntity<Map> response = restTemplate.getForEntity(url, Map.class);
            Map<String, Object> body = response.getBody();

            boolean online = response.getStatusCode().is2xxSuccessful();
            status.put("online", online);
            if (body != null) {
                status.put("capacityModelLoaded", Boolean.TRUE.equals(body.get("model_loaded")));
                status.put("capacityModelVersion", body.get("model_version"));
                status.put("flightTimeModelAvailable", Boolean.TRUE.equals(body.get("flight_time_model_available")));
                status.put("flightTimeModelVersion", body.getOrDefault(
                        "flight_time_model_version", "flight_time_lstm_v2"));
                status.put("airsimCapacityModelAvailable", Boolean.TRUE.equals(body.get("airsim_capacity_model_available")));
                status.put("airsimCapacityModelVersion", body.getOrDefault(
                        "airsim_capacity_model_version", "airsim_capacity_lstm_v2"));
                status.put("airsimCapacityTestMapePct", body.get("airsim_capacity_test_mape_pct"));
                status.put("airsimCapacityForecastHorizonS", body.getOrDefault(
                        "airsim_capacity_forecast_horizon_s", 10));
                status.put("quantizationEngine", body.get("quantization_engine"));
                status.put("energyV3Available",Boolean.TRUE.equals(body.get("energy_v3_available")));
                status.put("energyV3Status",body.get("energy_v3_status"));
            }
        } catch (Exception e) {
            log.warn("Python AI 推理服务离线: {}", e.getMessage());
            status.put("reason", "ai_service_unavailable");
        }
        return status;
    }

    @Override
    public boolean isAiServiceOnline() {
        return Boolean.TRUE.equals(getAiServiceStatus().get("online"));
    }
}
