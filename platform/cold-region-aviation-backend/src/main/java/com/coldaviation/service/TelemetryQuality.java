package com.coldaviation.service;

import com.coldaviation.entity.TelemetryData;
import java.time.Duration;
import java.util.*;

public final class TelemetryQuality {
    private TelemetryQuality() {}

    public record Window(List<TelemetryData> samples, String reason) {}

    public static String sampleReason(TelemetryData s) {
        String issue;
        if ((issue = range("envTemperature", s.getEnvTemperature(), -60, 60, false)) != null) return issue;
        if ((issue = range("windSpeed", s.getWindSpeed(), 0, 100, false)) != null) return issue;
        if ((issue = range("voltage", s.getVoltage(), 0, 100, true)) != null) return issue;
        if ((issue = range("current", s.getCurrent(), -1000, 1000, false)) != null) return issue;
        if ((issue = range("batteryLevel", s.getBatteryLevel(), 0, 100, false)) != null) return issue;
        if ((issue = range("speed", s.getSpeed(), 0, 200, false)) != null) return issue;
        if ((issue = range("altitude", s.getAltitude(), -1000, 20000, false)) != null) return issue;
        return range("remainingCapacityAh", s.getRemainingCapacityAh(), 0, 1000, true);
    }

    private static String range(String name, Double value, double min, double max, boolean strictMin) {
        if (value == null) return "missing_field: " + name;
        if (!Double.isFinite(value)) return "non_finite: " + name;
        if ((strictMin ? value <= min : value < min) || value > max) return "out_of_range: " + name;
        return null;
    }

    /** A usable window is the latest uninterrupted suffix, never a cross-run deque. */
    public static Window continuousSuffix(List<TelemetryData> candidates) {
        return continuousSuffix(candidates, false);
    }

    public static Window continuousSuffix(List<TelemetryData> candidates, boolean energyV3) {
        if (candidates.isEmpty()) return new Window(List.of(), "collecting_window: 0/30");
        List<TelemetryData> suffix = new ArrayList<>();
        String boundary = null;
        for (int i = candidates.size() - 1; i >= 0 && suffix.size() < 30; i--) {
            TelemetryData sample = candidates.get(i);
            String invalid = sampleReason(sample);
            if(invalid==null && energyV3) invalid=EnergyV3Contract.sampleReason(sample);
            if (invalid != null) { boundary = invalid; break; }
            if (!suffix.isEmpty()) {
                TelemetryData next = suffix.get(0);
                if (!Objects.equals(sample.getRunId(), next.getRunId())
                        || !Objects.equals(sample.getFlightId(), next.getFlightId())
                        || !Objects.equals(sample.getDroneId(), next.getDroneId())) {
                    boundary = "run_boundary"; break;
                }
                if (next.getSampleSeq() == null || sample.getSampleSeq() == null
                        || next.getSampleSeq() != sample.getSampleSeq() + 1) {
                    boundary = "sequence_gap"; break;
                }
                if (sample.getSourceTimeS() == null || next.getSourceTimeS() == null
                        || Math.abs(next.getSourceTimeS() - sample.getSourceTimeS() - 1.0) > 1e-6
                        || sample.getCollectTime() == null || next.getCollectTime() == null
                        || Duration.between(sample.getCollectTime(), next.getCollectTime()).toMillis() != 1000) {
                    boundary = "timestamp_gap"; break;
                }
            }
            suffix.add(0, sample);
        }
        String reason = suffix.size() == 30 ? null
                : (boundary == null ? "" : boundary + "; ") + "collecting_window: " + suffix.size() + "/30";
        return new Window(suffix, reason);
    }

    /** Canonical model inputs; omit database IDs and replay wall clocks from the fingerprint. */
    public static Map<String, Object> request(Long droneId, List<TelemetryData> samples) {
        List<Map<String, Object>> values = new ArrayList<>();
        TelemetryData first = samples.get(0);
        for (int i = 0; i < samples.size(); i++) {
            TelemetryData sample = samples.get(i);
            double seconds = sample.getSourceTimeS() != null && first.getSourceTimeS() != null
                    ? sample.getSourceTimeS() - first.getSourceTimeS()
                    : first.getCollectTime() != null && sample.getCollectTime() != null
                        ? Duration.between(first.getCollectTime(), sample.getCollectTime()).toMillis() / 1000.0 : i;
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("timestamp_s", seconds);
            item.put("env_temperature_C", sample.getEnvTemperature());
            item.put("wind_speed_ms", sample.getWindSpeed());
            item.put("voltage_V", sample.getVoltage());
            item.put("current_A", sample.getCurrent());
            item.put("battery_level_pct", sample.getBatteryLevel());
            item.put("speed_ms", sample.getSpeed());
            item.put("altitude_m", sample.getAltitude());
            item.put("remaining_capacity_Ah", sample.getRemainingCapacityAh());
            values.add(item);
        }
        Map<String, Object> request = new LinkedHashMap<>();
        request.put("drone_id", droneId);
        request.put("samples", values);
        return request;
    }
}
