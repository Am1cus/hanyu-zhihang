package com.coldaviation.service;

import com.coldaviation.entity.TelemetryData;
import com.coldaviation.exception.BusinessException;
import java.util.*;

/** Per-run research opt-in. No silent promotion of legacy requests or datasets. */
public final class EnergyV3Contract {
    public static final String MODEL="energy_residual_lstm_v3_rc1";
    public static final String SAMPLING="completed_1hz_bin_means_right_boundary_v1";
    public static final String DOMAIN="AIRSIM_FORMULA_BATTERY";
    private EnergyV3Contract() {}

    public static boolean selected(Map<String,Object> config) { return MODEL.equals(config.get("inference_method")); }
    public static void validate(Map<String,Object> config, String preprocessing) {
        Object method=config.get("inference_method");
        if(method!=null && !MODEL.equals(method) && !"airsim_capacity_lstm_v2".equals(method))
            throw new BusinessException(400,"不支持的实验模型，不能自动回退");
        if(!selected(config)) return;
        if(!SAMPLING.equals(config.get("sampling_contract")) || !SAMPLING.equals(preprocessing)
            || !DOMAIN.equals(config.get("battery_data_domain")) || !"research_shadow".equals(config.get("execution_mode")))
            throw new BusinessException(400,"V3需要完整秒均值、公式电池数据域和显式研究模式");
        if(config.get("quarantine_reason")!=null)
            throw new BusinessException(400,"已隔离架次不能作为正常V3实验");
    }

    public static String sampleReason(TelemetryData sample) {
        String[] names={"velocityX","velocityY","velocityZ","windX","windY","windZ"};
        Double[] values={sample.getVelocityX(),sample.getVelocityY(),sample.getVelocityZ(),sample.getWindX(),sample.getWindY(),sample.getWindZ()};
        for(int i=0;i<values.length;i++) {
            if(values[i]==null) return "missing_field: "+names[i];
            if(!Double.isFinite(values[i]) || Math.abs(values[i])>200) return "out_of_range: "+names[i];
        }
        return null;
    }

    public static Map<String,Object> request(Long drone, List<TelemetryData> window, Map<String,Object> config) {
        List<Map<String,Object>> samples=new ArrayList<>();
        for(var s:window) {
            Map<String,Object> row=new LinkedHashMap<>();
            row.put("flight_id",s.getFlightId());row.put("run_id",s.getRunId());row.put("available_at_s",s.getSourceTimeS());
            row.put("current",s.getCurrent());row.put("wind_speed",s.getWindSpeed());
            row.put("velocity_x",s.getVelocityX());row.put("velocity_y",s.getVelocityY());row.put("velocity_z",s.getVelocityZ());
            row.put("wind_x",s.getWindX());row.put("wind_y",s.getWindY());row.put("wind_z",s.getWindZ());
            row.put("remaining_capacity_ah",s.getRemainingCapacityAh());samples.add(row);
        }
        return Map.of("drone_id",drone,"sampling_contract",config.get("sampling_contract"),
                      "data_source",config.get("battery_data_domain"),"samples",samples);
    }

    public static Map<String,Object> unavailable(String reason) {
        Map<String,Object> result=new LinkedHashMap<>();
        result.put("valid",false);result.put("reason",reason);result.put("model_version",MODEL);
        result.put("predicted_capacity_Ah",null);result.put("predicted_consumption_Ah",null);result.put("forecast_horizon_s",10);
        result.put("research_status","frozen_candidate_pending_independent_confirmation");
        result.put("execution_mode","research_shadow");result.put("data_source",DOMAIN);
        result.put("validated_on_real_data",false);result.put("project_acceptance_passed",false);
        return result;
    }
}
