package com.coldaviation.service;

import com.coldaviation.entity.ExperimentRun;
import com.coldaviation.exception.BusinessException;
import com.coldaviation.repository.ExperimentRepository;
import com.coldaviation.websocket.TelemetryWebSocketHandler;
import jakarta.validation.constraints.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import java.time.LocalDateTime;
import java.util.*;

@Service
public class ExperimentService {
    private final ExperimentRepository repository;
    private final AiPredictionService ai;
    private final DroneService drones;
    private final TelemetryWebSocketHandler socket;

    public ExperimentService(ExperimentRepository repository, AiPredictionService ai, DroneService drones, TelemetryWebSocketHandler socket) {
        this.repository=repository; this.ai=ai; this.drones=drones; this.socket=socket;
    }

    public record CreateRun(
        @NotBlank @Size(max=100) String flightId,
        @NotNull @Positive Long droneId,
        @NotBlank @Size(max=50) String droneCode,
        @NotBlank @Pattern(regexp="AIRSIM") String dataSource,
        @NotBlank @Size(max=300) String sourceLabel,
        @NotBlank @Pattern(regexp="[a-f0-9]{64}") String sourceSha256,
        @NotBlank @Size(max=100) String preprocessingVersion,
        @NotNull Map<String,Object> configuration,
        @Min(1) @Max(100000) int expectedSamples) {}

    @Transactional
    public Map<String,Object> create(CreateRun input) {
        EnergyV3Contract.validate(input.configuration(),input.preprocessingVersion());
        var drone=drones.getById(input.droneId());
        if(drone==null || !Objects.equals(drone.getDroneCode(),input.droneCode()))
            throw new BusinessException(400,"数据源编号与登记设备不匹配");
        ExperimentRun run=new ExperimentRun();
        run.setRunId(UUID.randomUUID().toString());
        run.setFlightId(input.flightId()); run.setDroneId(input.droneId()); run.setDroneCode(input.droneCode());
        run.setDataSource(input.dataSource()); run.setSourceLabel(input.sourceLabel()); run.setSourceSha256(input.sourceSha256());
        run.setPreprocessingVersion(input.preprocessingVersion());
        String config=repository.encode(input.configuration());
        if(config.length()>20000) throw new BusinessException(400,"预处理配置过长");
        run.setConfigJson(config); run.setConfigSha256(ExperimentRepository.sha256(config));
        run.setExpectedSamples(input.expectedSamples()); run.setSampleCount(0); run.setStatus("RUNNING");
        run.setCollectStartTime(LocalDateTime.now().withNano(0)); run.setCreatedAt(LocalDateTime.now());
        repository.create(run);
        afterCommit(() -> socket.broadcast(Map.of("type","run-started","runId",run.getRunId(),"flightId",run.getFlightId())));
        return repository.summary(run);
    }

    public Map<String,Object> detail(String id) { return repository.summary(repository.run(id,false)); }

    @Transactional
    public Map<String,Object> finish(String id, String status, String error) {
        ExperimentRun run=repository.run(id,true);
        if(status==null || !Set.of("COMPLETED","INTERRUPTED").contains(status)) throw new BusinessException(400,"不支持的运行状态");
        if("COMPLETED".equals(run.getStatus())) return repository.summary(run);
        if("COMPLETED".equals(status) && !Objects.equals(run.getExpectedSamples(),run.getSampleCount()))
            throw new BusinessException(409,"实际记录数与预计样本数不一致，不能标记完成");
        if(error!=null && error.length()>500) error=error.substring(0,500);
        repository.finish(id,status,error);
        afterCommit(() -> socket.broadcast(Map.of("type","run-finished","runId",id,"status",status)));
        return detail(id);
    }

    @SuppressWarnings("unchecked")
    public Map<String,Object> recheck(String id, int seq) {
        repository.run(id,false);
        Map<String,Object> archived=repository.prediction(id,seq);
        Map<String,Object> original=(Map<String,Object>)archived.get("response");
        if(!Boolean.TRUE.equals(original.get("valid"))) throw new BusinessException(400,"该窗口原预测不可用，不能作一致性复算");
        Map<String,Object> fresh=ai.predictCapacityRequest((Map<String,Object>)archived.get("request"));
        boolean sameArtifacts=original.get("model_sha256")!=null && original.get("scaler_sha256")!=null
            && Objects.equals(original.get("model_sha256"),fresh.get("model_sha256"))
            && Objects.equals(original.get("scaler_sha256"),fresh.get("scaler_sha256"))
            && Objects.equals(original.get("model_version"),fresh.get("model_version"));
        boolean consistent=sameArtifacts && Boolean.TRUE.equals(fresh.get("valid"))
            && close(original.get("predicted_consumption_Ah"),fresh.get("predicted_consumption_Ah"))
            && close(original.get("predicted_capacity_Ah"),fresh.get("predicted_capacity_Ah"));
        Map<String,Object> report=new LinkedHashMap<>();
        report.put("recheckId",UUID.randomUUID().toString());report.put("runId",id);report.put("sampleSeq",seq);
        report.put("inputSha256",archived.get("inputSha256"));report.put("sameArtifacts",sameArtifacts);
        report.put("consistent",consistent);report.put("toleranceAh",1e-6);
        report.put("reason",!Boolean.TRUE.equals(fresh.get("valid")) ? "ai_unavailable" : !sameArtifacts ? "artifact_mismatch" : consistent ? "matched" : "output_mismatch");
        report.put("original",original);report.put("recomputed",fresh);report.put("checkedAt",LocalDateTime.now());
        repository.saveRecheck(id,seq,report);
        return report;
    }

    private boolean close(Object a,Object b) {
        return a instanceof Number x && b instanceof Number y && Double.isFinite(x.doubleValue())
            && Double.isFinite(y.doubleValue()) && Math.abs(x.doubleValue()-y.doubleValue())<=1e-6;
    }

    public static void afterCommit(Runnable action) {
        if(!TransactionSynchronizationManager.isSynchronizationActive()) { action.run(); return; }
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override public void afterCommit() { action.run(); }
        });
    }
}
