package com.coldaviation.service.impl;

import com.coldaviation.entity.TelemetryData;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;

class AiPredictionServiceImplTest {

    private final AiPredictionServiceImpl service = new AiPredictionServiceImpl();

    @Test
    void rejectsIncompleteWindowWithoutCallingRemoteService() {
        Map<String, Object> result = service.predictFlightTime(2L, List.of());

        assertFalse((Boolean) result.get("valid"));
        assertNull(result.get("remaining_flight_time_s"));
        assertEquals("insufficient_samples: 需要最近30条1Hz遥测", result.get("reason"));
    }

    @Test
    void rejectsMissingTelemetryFieldsWithoutInventingPrediction() {
        List<TelemetryData> samples = new ArrayList<>();
        for (int index = 0; index < 30; index++) {
            samples.add(new TelemetryData());
        }

        Map<String, Object> result = service.predictFlightTime(2L, samples);

        assertFalse((Boolean) result.get("valid"));
        assertNull(result.get("remaining_flight_time_s"));
        assertEquals("incomplete_telemetry: 温度、风速、电压、电流、电量、速度和高度均为必填", result.get("reason"));
    }

    @Test
    void legacySingleSampleEndpointIsExplicitlyDeprecated() {
        Map<String, Object> result = service.predictPowerDecay(2L, 11.4, 12.0, -25.0, 8.0, 90.0);

        assertFalse((Boolean) result.get("valid"));
        assertNull(result.get("remaining_flight_time_s"));
    }

    @Test
    void airsimCapacityRequiresThirtySecondWindow() {
        Map<String, Object> result = service.predictAirSimCapacity(2L, List.of());

        assertFalse((Boolean) result.get("valid"));
        assertNull(result.get("predicted_capacity_Ah"));
        assertEquals("airsim_capacity_lstm_v2", result.get("model_version"));
        assertEquals("insufficient_samples: 需要最近30条1Hz遥测", result.get("reason"));
    }
}
