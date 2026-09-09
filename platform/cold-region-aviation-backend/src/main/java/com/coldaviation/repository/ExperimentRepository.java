package com.coldaviation.repository;

import com.coldaviation.entity.ExperimentRun;
import com.coldaviation.entity.TelemetryData;
import com.coldaviation.exception.BusinessException;
import com.coldaviation.service.EnergyV3Contract;
import com.coldaviation.service.TelemetryQuality;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import org.springframework.jdbc.core.BeanPropertyRowMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.LocalDateTime;
import java.util.*;

@Repository
public class ExperimentRepository {
    private final JdbcTemplate jdbc;
    private final ObjectMapper json;

    public ExperimentRepository(JdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.json = mapper.copy().configure(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS, true);
    }

    public String encode(Object value) {
        try { return json.writeValueAsString(value); }
        catch (Exception e) { throw new IllegalArgumentException("无法序列化实验记录", e); }
    }

    public Map<String, Object> decode(String value) {
        try { return json.readValue(value, new TypeReference<Map<String, Object>>() {}); }
        catch (Exception e) { throw new IllegalStateException("实验档案JSON损坏", e); }
    }

    public static String sha256(String text) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(text.getBytes(StandardCharsets.UTF_8))); }
        catch (Exception e) { throw new IllegalStateException(e); }
    }

    public void create(ExperimentRun r) {
        jdbc.update("INSERT INTO experiment_run (run_id,flight_id,drone_id,drone_code,data_source,source_label,source_sha256,config_sha256,preprocessing_version,config_json,expected_samples,sample_count,status,collect_start_time,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            r.getRunId(),r.getFlightId(),r.getDroneId(),r.getDroneCode(),r.getDataSource(),r.getSourceLabel(),r.getSourceSha256(),r.getConfigSha256(),r.getPreprocessingVersion(),r.getConfigJson(),r.getExpectedSamples(),0,"RUNNING",r.getCollectStartTime(),r.getCreatedAt());
    }

    public ExperimentRun run(String id, boolean lock) {
        var rows = jdbc.query("SELECT * FROM experiment_run WHERE run_id=?" + (lock ? " FOR UPDATE" : ""),
                BeanPropertyRowMapper.newInstance(ExperimentRun.class), id);
        if (rows.isEmpty()) throw new BusinessException(404, "实验记录不存在");
        return rows.get(0);
    }

    public Map<String, Object> list(int page, int size, String flightId) {
        String where = flightId == null || flightId.isBlank() ? "" : " WHERE flight_id=?";
        Object[] args = where.isEmpty() ? new Object[]{} : new Object[]{flightId};
        Long total = jdbc.queryForObject("SELECT COUNT(*) FROM experiment_run" + where, Long.class, args);
        List<Object> params = new ArrayList<>(Arrays.asList(args)); params.add(size); params.add((page-1)*size);
        var records = jdbc.query("SELECT * FROM experiment_run" + where + " ORDER BY created_at DESC,run_id DESC LIMIT ? OFFSET ?",
                BeanPropertyRowMapper.newInstance(ExperimentRun.class), params.toArray());
        return Map.of("records", records.stream().map(this::summary).toList(), "total", total, "current", page, "size", size);
    }

    public Map<String, Object> summary(ExperimentRun run) {
        Map<String, Object> result = decode(encode(run));
        result.remove("configJson");
        result.put("configuration", decode(run.getConfigJson()));
        result.put("metrics", jdbc.queryForMap("SELECT COUNT(*) AS prediction_count, MAX(sample_seq) AS last_sample_seq, SUM(CASE WHEN valid=TRUE THEN 1 ELSE 0 END) AS valid_count, COUNT(absolute_error_ah) AS verified_count, AVG(absolute_error_ah)*1000 AS mae_mah, AVG(percentage_error) AS mape_pct FROM prediction_record WHERE run_id=?", run.getRunId()));
        if(EnergyV3Contract.selected(decode(run.getConfigJson()))) result.put("baselineMetrics",baselineMetrics(run.getRunId()));
        return result;
    }

    /** Compare all three methods on the exact same archived, arrived labels. */
    private Map<String,Object> baselineMetrics(String runId) {
        Map<String,double[]> sums=new LinkedHashMap<>();
        for(String name:List.of("lstm","history_10s","mean_current_20s")) sums.put(name,new double[4]);
        jdbc.query("SELECT response_json,actual_consumption_ah FROM prediction_record WHERE run_id=? AND label_status='verified' AND actual_consumption_ah>0.000000001",rs -> {
            Map<String,Object> p=decode(rs.getString(1));
            if(!(p.get("baselines") instanceof Map<?,?> b)) return;
            Object[] values={p.get("predicted_consumption_Ah"),b.get("history_10s"),b.get("mean_current_20s")};
            for(Object value:values) if(!(value instanceof Number n) || !Double.isFinite(n.doubleValue())) return;
            double actual=rs.getDouble(2);int i=0;
            for(double[] sum:sums.values()) {
                double error=((Number)values[i++]).doubleValue()-actual;
                sum[0]++;sum[1]+=Math.abs(error)*1000;sum[2]+=Math.abs(error)/actual*100;sum[3]+=error*error*1000000;
            }
        },runId);
        Map<String,Object> result=new LinkedHashMap<>();
        sums.forEach((name,s)->{
            Map<String,Object> m=new LinkedHashMap<>();m.put("count",(int)s[0]);
            m.put("mae_mah",s[0]>0?s[1]/s[0]:null);m.put("mape_pct",s[0]>0?s[2]/s[0]:null);
            m.put("rmse_mah",s[0]>0?Math.sqrt(s[3]/s[0]):null);result.put(name,m);
        });
        return result;
    }

    public List<Map<String, Object>> events(String runId, int afterSeq, int limit) {
        return jdbc.query("SELECT event_json,actual_consumption_ah,absolute_error_ah,percentage_error,label_status FROM prediction_record WHERE run_id=? AND sample_seq>? ORDER BY sample_seq LIMIT ?", (rs, n) -> {
            Map<String,Object> event = decode(rs.getString("event_json"));
            Map<String,Object> verification = new LinkedHashMap<>();
            verification.put("actual_consumption_Ah",rs.getObject("actual_consumption_ah"));
            verification.put("absolute_error_Ah",rs.getObject("absolute_error_ah"));
            verification.put("percentage_error",rs.getObject("percentage_error"));
            verification.put("status",rs.getString("label_status"));
            event.put("verification",verification);
            return event;
        }, runId, afterSeq, limit);
    }

    public List<Object> latestSnapshot() {
        var ids = jdbc.queryForList("SELECT run_id FROM experiment_run WHERE sample_count>0 ORDER BY created_at DESC,run_id DESC LIMIT 1", String.class);
        if (ids.isEmpty()) return List.of();
        String id = ids.get(0);
        Integer max = jdbc.queryForObject("SELECT MAX(sample_seq) FROM prediction_record WHERE run_id=?",Integer.class,id);
        return new ArrayList<>(events(id, Math.max(-1, max - 1800), 1800));
    }

    public List<TelemetryData> window(String runId, int seq) {
        var rows = jdbc.query("SELECT * FROM telemetry_data WHERE run_id=? AND sample_seq<=? ORDER BY sample_seq DESC LIMIT 30",
                BeanPropertyRowMapper.newInstance(TelemetryData.class), runId, seq);
        Collections.reverse(rows);
        return rows;
    }

    public TelemetryData existing(String runId, int seq) {
        var rows = jdbc.query("SELECT * FROM telemetry_data WHERE run_id=? AND sample_seq=?",
                BeanPropertyRowMapper.newInstance(TelemetryData.class),runId,seq);
        return rows.isEmpty() ? null : rows.get(0);
    }

    public TelemetryData last(String runId) {
        var rows = jdbc.query("SELECT * FROM telemetry_data WHERE run_id=? ORDER BY sample_seq DESC LIMIT 1",
                BeanPropertyRowMapper.newInstance(TelemetryData.class), runId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    public void appendPrediction(TelemetryData t, Map<String,Object> prediction, Map<String,Object> request,
                                 List<TelemetryData> window, Map<String,Object> event) {
        String input = encode(request);
        jdbc.update("INSERT INTO prediction_record (telemetry_id,run_id,sample_seq,source_time_s,target_source_time_s,valid,reason,window_start_seq,window_end_seq,input_sha256,request_json,response_json,event_json,model_version,model_sha256,scaler_sha256,current_capacity_ah,predicted_consumption_ah,predicted_capacity_ah,label_status,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            t.getId(),t.getRunId(),t.getSampleSeq(),t.getSourceTimeS(),t.getSourceTimeS()+10,
            Boolean.TRUE.equals(prediction.get("valid")), prediction.get("reason"),
            window.isEmpty() ? null : window.get(0).getSampleSeq(), t.getSampleSeq(),
            sha256(input), input, encode(prediction), encode(event),
            prediction.get("model_version"),prediction.get("model_sha256"),prediction.get("scaler_sha256"),
            finite(t.getRemainingCapacityAh()), prediction.get("predicted_consumption_Ah"),prediction.get("predicted_capacity_Ah"),
            Boolean.TRUE.equals(prediction.get("valid")) ? "pending" : "prediction_unavailable", LocalDateTime.now());
        jdbc.update("UPDATE experiment_run SET sample_count=sample_count+1,status='RUNNING',last_error=NULL,finished_at=NULL WHERE run_id=?",t.getRunId());
    }

    private Double finite(Double x) { return x != null && Double.isFinite(x) ? x : null; }

    public void verifyArrivedTarget(TelemetryData target) {
        var config=decode(run(target.getRunId(),false).getConfigJson());
        if(EnergyV3Contract.selected(config)) {
            var future=jdbc.query("SELECT * FROM telemetry_data WHERE run_id=? AND source_time_s>=? AND source_time_s<=? ORDER BY source_time_s",
                BeanPropertyRowMapper.newInstance(TelemetryData.class),target.getRunId(),target.getSourceTimeS()-10,target.getSourceTimeS());
            boolean complete=future.size()==11;
            for(int i=0;complete && i<future.size();i++) {
                var row=future.get(i);
                complete=TelemetryQuality.sampleReason(row)==null && EnergyV3Contract.sampleReason(row)==null;
                if(i>0) complete=complete && Math.abs(row.getSourceTimeS()-future.get(i-1).getSourceTimeS()-1)<1e-6
                    && row.getSampleSeq()==future.get(i-1).getSampleSeq()+1
                    && row.getRemainingCapacityAh()<=future.get(i-1).getRemainingCapacityAh()+1e-9;
            }
            if(!complete) {
                jdbc.update("UPDATE prediction_record SET label_status='invalid_target' WHERE run_id=? AND target_source_time_s=? AND valid=TRUE",target.getRunId(),target.getSourceTimeS());
                return;
            }
        }
        Double capacity = finite(target.getRemainingCapacityAh());
        if (capacity == null || capacity < 0 || capacity > 1000) {
            jdbc.update("UPDATE prediction_record SET label_status='invalid_target' WHERE run_id=? AND target_source_time_s=? AND valid=TRUE",
                target.getRunId(),target.getSourceTimeS());
            return;
        }
        // Future observations only annotate archived predictions; never overwrite their outputs.
        jdbc.update("UPDATE prediction_record SET actual_consumption_ah=current_capacity_ah-?, absolute_error_ah=ABS(predicted_consumption_ah-(current_capacity_ah-?)), percentage_error=CASE WHEN ABS(current_capacity_ah-?)>0.000000001 THEN ABS(predicted_consumption_ah-(current_capacity_ah-?))/ABS(current_capacity_ah-?)*100 ELSE NULL END, label_status='verified' WHERE run_id=? AND target_source_time_s=? AND valid=TRUE AND current_capacity_ah>=?",
            capacity,capacity,capacity,capacity,capacity,target.getRunId(),target.getSourceTimeS(),capacity);
        jdbc.update("UPDATE prediction_record SET label_status='invalid_target' WHERE run_id=? AND target_source_time_s=? AND valid=TRUE AND current_capacity_ah<?",
            target.getRunId(),target.getSourceTimeS(),capacity);
    }

    public void finish(String runId, String status, String error) {
        jdbc.update("UPDATE experiment_run SET status=?,last_error=?,finished_at=? WHERE run_id=?",status,error,LocalDateTime.now(),runId);
    }

    public Map<String,Object> prediction(String runId, int seq) {
        var rows = jdbc.query("SELECT request_json,response_json,input_sha256 FROM prediction_record WHERE run_id=? AND sample_seq=?", (rs,n) -> {
            Map<String,Object> result = new LinkedHashMap<>();
            result.put("request",decode(rs.getString("request_json")));
            result.put("response",decode(rs.getString("response_json")));
            result.put("inputSha256",rs.getString("input_sha256"));
            return result;
        },runId,seq);
        if(rows.isEmpty()) throw new BusinessException(404,"该窗口没有存档预测");
        return rows.get(0);
    }

    public void saveRecheck(String runId, int seq, Map<String,Object> report) {
        jdbc.update("INSERT INTO prediction_recheck(recheck_id,run_id,sample_seq,report_json,created_at) VALUES (?,?,?,?,?)",
            report.get("recheckId"),runId,seq,encode(report),LocalDateTime.now());
    }

    public List<Map<String,Object>> rechecks(String runId) {
        return jdbc.query("SELECT report_json FROM prediction_recheck WHERE run_id=? ORDER BY created_at DESC LIMIT 50",
                (rs,n)->decode(rs.getString(1)),runId);
    }
}
