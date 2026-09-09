package com.coldaviation.service.impl;

import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.coldaviation.common.Constants;
import com.coldaviation.entity.TelemetryData;
import com.coldaviation.entity.WarningRecord;
import com.coldaviation.mapper.TelemetryMapper;
import com.coldaviation.exception.BusinessException;
import com.coldaviation.repository.ExperimentRepository;
import com.coldaviation.service.*;
import com.coldaviation.websocket.TelemetryWebSocketHandler;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.LocalDateTime;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.TimeUnit;

@Slf4j
@Service
public class TelemetryServiceImpl extends ServiceImpl<TelemetryMapper, TelemetryData> implements TelemetryService {
    private final RedisTemplate<String,Object> redis;
    private final TelemetryWebSocketHandler socket;
    private final AiPredictionService ai;
    private final DroneService drones;
    private final WarningService warnings;
    private final ExperimentRepository experiments;

    public TelemetryServiceImpl(RedisTemplate<String,Object> redis, TelemetryWebSocketHandler socket,
            AiPredictionService ai, DroneService drones, WarningService warnings, ExperimentRepository experiments) {
        this.redis=redis;this.socket=socket;this.ai=ai;this.drones=drones;this.warnings=warnings;this.experiments=experiments;
    }

    @Override
    @Transactional
    public boolean saveTelemetry(TelemetryData data) {
        if(data.getRunId()==null || data.getFlightId()==null || data.getSampleSeq()==null
                || data.getSampleSeq()<0 || data.getSourceTimeS()==null || !Double.isFinite(data.getSourceTimeS())
                || data.getSourceTimeS()<0 || data.getSourceTimeS()>604800 || data.getCollectTime()==null)
            throw new BusinessException(400,"需要runId、flightId、sampleSeq、sourceTimeS和collectTime；请先创建实验记录");
        // Reject non-JSON finite numbers rather than silently turning them into zero/null.
        for(var field : TelemetryData.class.getDeclaredFields()) {
            if(field.getType()==Double.class) {
                try {
                    field.setAccessible(true);
                    Double value=(Double)field.get(data);
                    if(value!=null && !Double.isFinite(value)) throw new BusinessException(400,"非有限数值: "+field.getName());
                } catch(IllegalAccessException e) { throw new IllegalStateException(e); }
            }
        }
        // Serialize concurrent requests for one run using a database lock, including after restart.
        var run=experiments.run(data.getRunId(),true);
        if(!Objects.equals(run.getDroneId(),data.getDroneId()) || !Objects.equals(run.getDroneCode(),data.getDroneCode())
                || !Objects.equals(run.getFlightId(),data.getFlightId()))
            throw new BusinessException(400,"遥测设备或架次与runId不匹配");
        if(data.getSampleSeq()>=run.getExpectedSamples()) throw new BusinessException(400,"sampleSeq超出本次记录范围");
        Duration interval=Duration.between(run.getCollectStartTime(),data.getCollectTime());
        double elapsed=interval.getSeconds()+interval.getNano()/1e9;
        if(Math.abs(elapsed-data.getSourceTimeS())>1e-6)
            throw new BusinessException(400,"collectTime必须等于本次起始时间加sourceTimeS，不能用回放接收时间代替");
        data.setId(null); data.setCreateTime(null); data.setPayloadSha256(null);
        String payloadHash=ExperimentRepository.sha256(experiments.encode(data));
        var existing=experiments.existing(data.getRunId(),data.getSampleSeq());
        if(existing!=null) {
            if(!payloadHash.equals(existing.getPayloadSha256())) throw new BusinessException(409,"重复sampleSeq内容冲突，原记录未修改");
            return true; // Idempotent retry: no inference, duplicate warning, or broadcast.
        }
        if("COMPLETED".equals(run.getStatus())) throw new BusinessException(409,"已完成实验不允许追加新样本");
        var last=experiments.last(data.getRunId());
        if(last!=null && (data.getSampleSeq()<=last.getSampleSeq() || data.getSourceTimeS()<=last.getSourceTimeS()))
            throw new BusinessException(409,"乱序或重复源时间，记录未写入");
        data.setPayloadSha256(payloadHash);
        if(!save(data)) return false;
        var configuration=experiments.decode(run.getConfigJson());
        boolean energyV3=EnergyV3Contract.selected(configuration);
        var checked=TelemetryQuality.continuousSuffix(experiments.window(data.getRunId(),data.getSampleSeq()),energyV3);
        Map<String,Object> request=checked.samples().size()==30
                ? (energyV3 ? EnergyV3Contract.request(data.getDroneId(),checked.samples(),configuration)
                            : TelemetryQuality.request(data.getDroneId(),checked.samples())) : Map.of();
        Map<String,Object> prediction=checked.reason()==null
                ? (energyV3 ? ai.predictCapacityRequest(request) : ai.predictAirSimCapacity(data.getDroneId(),checked.samples()))
                : (energyV3 ? EnergyV3Contract.unavailable(checked.reason()) : unavailable(checked.reason()));
        prediction=new LinkedHashMap<>(prediction);
        prediction.put("window_samples",checked.samples().size());
        prediction.put("window_start_seq",checked.samples().isEmpty()?null:checked.samples().get(0).getSampleSeq());
        prediction.put("window_end_seq",data.getSampleSeq());
        prediction.put("target_source_time_s",data.getSourceTimeS()+10);
        prediction.put("evaluation_role",configuration.getOrDefault("evaluation_role","legacy_V2"));
        prediction.put("sampling_contract",configuration.getOrDefault("sampling_contract",run.getPreprocessingVersion()));
        prediction.put("input_sha256",ExperimentRepository.sha256(experiments.encode(request)));
        Map<String,Object> event=new LinkedHashMap<>();
        event.put("type","telemetry");event.put("runId",run.getRunId());event.put("flightId",run.getFlightId());
        event.put("telemetry",data);event.put("prediction",prediction);event.put("serverTime",LocalDateTime.now());
        experiments.appendPrediction(data,prediction,request,checked.samples(),event);
        experiments.verifyArrivedTarget(data);
        createWarnings(data);
        drones.updateDroneTelemetry(data.getDroneId(),data.getLatitude(),data.getLongitude(),data.getAltitude(),data.getBatteryLevel());
        ExperimentService.afterCommit(() -> { cache(data); socket.broadcast(event); });
        return true;
    }

    private Map<String,Object> unavailable(String reason) {
        Map<String,Object> value=new LinkedHashMap<>();
        value.put("valid",false);value.put("reason",reason);value.put("predicted_capacity_Ah",null);
        value.put("predicted_consumption_Ah",null);value.put("forecast_horizon_s",10);
        value.put("model_version","airsim_capacity_lstm_v2");value.put("data_source","AirSim simulation");
        value.put("validated_on_real_data",false);
        return value;
    }

    @Override
    public TelemetryData getLatestByDroneId(Long droneId) {
        return baseMapper.selectLatestByDroneId(droneId);
    }
    @Override
    public List<TelemetryData> getByTimeRange(Long id,LocalDateTime start,LocalDateTime end) {
        return baseMapper.selectByTimeRange(id,start,end);
    }
    @Override
    public TelemetryData getRealtimeFromCache(Long id) {
        // Database remains authoritative across service restarts and Redis outages.
        return getLatestByDroneId(id);
    }
    private void cache(TelemetryData data) {
        try { redis.opsForValue().set(Constants.REDIS_KEY_TELEMETRY+data.getDroneId(),data,30,TimeUnit.SECONDS); }
        catch(Exception e) { log.debug("Redis不可用，实验记录已持久化"); }
    }
    @Override
    public void resetRuntimeState() {
        // Reset only the display feed. Durable runs, predictions and warnings are never deleted.
    }

    private void createWarnings(TelemetryData data) {
        if(data.getEnvTemperature()!=null && data.getEnvTemperature()>=-60 && data.getEnvTemperature()<=-25)
            warn(data,"TEMPERATURE",2,"环境温度达到-25°C及以下");
        if(data.getWindSpeed()!=null && data.getWindSpeed()>=8 && data.getWindSpeed()<=100)
            warn(data,"WIND",2,"风速达到8m/s及以上");
        if(data.getBatteryLevel()!=null && data.getBatteryLevel()>=0 && data.getBatteryLevel()<=20)
            warn(data,"BATTERY",4,"电池电量低于安全返航阈值");
    }
    private void warn(TelemetryData data,String type,int level,String title) {
        if(warnings.lambdaQuery().eq(WarningRecord::getRunId,data.getRunId()).eq(WarningRecord::getWarningType,type)
                .ge(WarningRecord::getWarningTime,LocalDateTime.now().minusSeconds(60)).count()>0) return;
        WarningRecord warning=new WarningRecord();
        warning.setRunId(data.getRunId());warning.setFlightId(data.getFlightId());
        warning.setDroneId(data.getDroneId());warning.setDroneCode(data.getDroneCode());
        warning.setWarningType(type);warning.setWarningLevel(level);warning.setTitle(title);
        warning.setMessage("AirSim遥测阈值触发 · "+data.getFlightId()+" · 源时间 "+data.getSourceTimeS()+"s");
        warning.setTriggerTemperature(data.getEnvTemperature());warning.setTriggerBatteryLevel(data.getBatteryLevel());
        warning.setTriggerWindSpeed(data.getWindSpeed());warning.setTriggerLatitude(data.getLatitude());warning.setTriggerLongitude(data.getLongitude());
        warnings.createWarning(warning);
    }
}
