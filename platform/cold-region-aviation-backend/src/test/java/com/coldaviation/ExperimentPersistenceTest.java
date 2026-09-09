package com.coldaviation;

import com.coldaviation.entity.TelemetryData;
import com.coldaviation.repository.ExperimentRepository;
import com.coldaviation.service.AiPredictionService;
import com.coldaviation.service.ExperimentService;
import com.coldaviation.service.EnergyV3Contract;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import java.time.LocalDateTime;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={"spring.datasource.url=jdbc:h2:mem:persistence-tests;MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1","spring.data.redis.repositories.enabled=false"})
@ActiveProfiles("demo")
@AutoConfigureMockMvc
class ExperimentPersistenceTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;
    @Autowired ExperimentRepository repository;
    @Autowired ExperimentService service;
    @MockBean AiPredictionService ai;
    @MockBean(name="redisTemplate") RedisTemplate<String,Object> redis;
    final AtomicInteger calls=new AtomicInteger();
    final String modelHash="a".repeat(64), scalerHash="b".repeat(64);

    @BeforeEach
    @SuppressWarnings("unchecked")
    void configure() {
        when(redis.opsForValue()).thenReturn(mock(ValueOperations.class));
        when(ai.predictAirSimCapacity(anyLong(),anyList())).thenAnswer(invocation -> {
            calls.incrementAndGet();
            List<TelemetryData> samples=invocation.getArgument(1);
            return prediction(samples.get(29).getRemainingCapacityAh(),modelHash);
        });
        when(ai.predictCapacityRequest(anyMap())).thenAnswer(invocation -> {
            Map<String,Object> request=invocation.getArgument(0);
            List<Map<String,Object>> samples=(List<Map<String,Object>>)request.get("samples");
            return prediction(((Number)samples.get(29).get("remaining_capacity_Ah")).doubleValue(),modelHash);
        });
    }

    Map<String,Object> prediction(double current,String hash) {
        return new LinkedHashMap<>(Map.of("valid",true,"predicted_consumption_Ah",.01,
                "predicted_capacity_Ah",current-.01,"model_version","test_model","model_sha256",hash,
                "scaler_sha256",scalerHash,"forecast_horizon_s",10));
    }

    Map<String,Object> createRun(int count) throws Exception {
        return createRun(count,Map.of("interpolation",false),"test-v1");
    }
    Map<String,Object> createRun(int count,Map<String,Object> config,String preprocessing) throws Exception {
        Map<String,Object> request=Map.of("flightId","flight_test","droneId",2,"droneCode","AIRSIM-001",
                "dataSource","AIRSIM","sourceLabel","fixture","sourceSha256","c".repeat(64),
                "preprocessingVersion",preprocessing,"configuration",config,"expectedSamples",count);
        var response=mvc.perform(post("/api/runs").contentType("application/json").content(json.writeValueAsString(request)))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        return json.readValue(response,Map.class).get("data") instanceof Map data ? data : Map.of();
    }

    Map<String,Object> sample(Map<String,Object> run,int seq,int sourceTime) {
        var sample=new LinkedHashMap<String,Object>();
        sample.put("runId",run.get("runId"));sample.put("flightId","flight_test");
        sample.put("droneId",2);sample.put("droneCode","AIRSIM-001");
        sample.put("sampleSeq",seq);sample.put("sourceTimeS",sourceTime);
        sample.put("collectTime",LocalDateTime.parse((String)run.get("collectStartTime")).plusSeconds(sourceTime).toString());
        sample.put("envTemperature",-10);sample.put("windSpeed",0);sample.put("voltage",11);
        sample.put("current",3.6);sample.put("batteryLevel",90);sample.put("speed",1);sample.put("altitude",10);
        sample.put("remainingCapacityAh",1-sourceTime*.001);
        return sample;
    }
    void send(Map<String,Object> sample,int statusCode) throws Exception {
        mvc.perform(post("/api/telemetry").contentType("application/json").content(json.writeValueAsString(sample)))
                .andExpect(status().is(statusCode));
    }
    void fill(Map<String,Object> run,int count) throws Exception {
        for(int seq=0;seq<count;seq++) send(sample(run,seq,seq),200);
    }

    Map<String,Object> energyRun(int count) throws Exception {
        return createRun(count,Map.of("inference_method",EnergyV3Contract.MODEL,"sampling_contract",EnergyV3Contract.SAMPLING,
            "battery_data_domain",EnergyV3Contract.DOMAIN,"execution_mode","research_shadow","evaluation_role","fixture"),EnergyV3Contract.SAMPLING);
    }
    Map<String,Object> energySample(Map<String,Object> run,int seq) {
        var row=sample(run,seq,seq+1);
        for(String key:List.of("velocityX","velocityY","velocityZ","windX","windY","windZ")) row.put(key,0.0);
        row.put("velocityX",1.0);
        return row;
    }
    @SuppressWarnings("unchecked")
    void energyAi() {
        doAnswer(invocation->{
            calls.incrementAndGet();Map<String,Object> request=invocation.getArgument(0);
            assertEquals(EnergyV3Contract.SAMPLING,request.get("sampling_contract"));
            var samples=(List<Map<String,Object>>)request.get("samples");
            assertEquals(30,samples.size());assertTrue(samples.get(29).containsKey("wind_x"));
            var p=prediction(((Number)samples.get(29).get("remaining_capacity_ah")).doubleValue(),modelHash);
            p.put("model_version",EnergyV3Contract.MODEL);p.put("execution_mode","research_shadow");
            p.put("baselines",Map.of("history_10s",.01,"mean_current_20s",.012));return p;
        }).when(ai).predictCapacityRequest(anyMap());
    }

    @Test
    @SuppressWarnings("unchecked")
    void energyArchivesVectorContractBaselinesAndRechecksWithoutLegacyPromotion() throws Exception {
        energyAi();var run=energyRun(40);String id=(String)run.get("runId");
        for(int i=0;i<40;i++)send(energySample(run,i),200);
        assertEquals(11,calls.get());verify(ai,never()).predictAirSimCapacity(anyLong(),anyList());
        assertEquals(1.0,repository.existing(id,29).getVelocityX());
        var before=repository.prediction(id,29);
        send(energySample(run,29),200);assertEquals(11,calls.get());
        assertEquals(true,service.recheck(id,29).get("consistent"));
        assertEquals(before,repository.prediction(id,29));
        var metrics=(Map<String,Object>)service.detail(id).get("baselineMetrics");
        var lstm=(Map<String,Object>)metrics.get("lstm");
        assertEquals(1,((Number)lstm.get("count")).intValue());
        assertEquals(0,((Number)lstm.get("mape_pct")).doubleValue(),1e-9);
        assertEquals(20,((Number)((Map<?,?>)metrics.get("mean_current_20s")).get("mape_pct")).doubleValue(),1e-9);
        service.finish(id,"COMPLETED",null);
    }

    @Test
    void energyMissingVectorIsStoredAsUnavailableAndBreaksTheWindow() throws Exception {
        energyAi();var run=energyRun(61);String id=(String)run.get("runId");
        for(int i=0;i<30;i++)send(energySample(run,i),200);
        var missing=energySample(run,30);missing.remove("windX");send(missing,200);
        var unavailable=(Map<?,?>)repository.prediction(id,30).get("response");
        assertEquals(EnergyV3Contract.MODEL,unavailable.get("model_version"));
        assertEquals(false,unavailable.get("valid"));assertNull(unavailable.get("predicted_consumption_Ah"));
        assertTrue(unavailable.get("reason").toString().contains("windX"));
        for(int i=31;i<60;i++)send(energySample(run,i),200);
        assertEquals(1,calls.get());send(energySample(run,60),200);assertEquals(2,calls.get());
    }

    @Test
    void energyFutureLabelCannotBridgeMissingSeconds() throws Exception {
        energyAi();var run=energyRun(40);String id=(String)run.get("runId");
        for(int i=0;i<40;i++)if(i!=34)send(energySample(run,i),200);
        var event=repository.events(id,28,1).get(0);
        assertEquals("invalid_target",((Map<?,?>)event.get("verification")).get("status"));
    }

    @Test
    void energyOfflineNeverFallsBackToLegacyOrCreatesAnOutput() throws Exception {
        doReturn(EnergyV3Contract.unavailable("ai_service_unavailable")).when(ai).predictCapacityRequest(anyMap());
        var run=energyRun(30);for(int i=0;i<30;i++)send(energySample(run,i),200);
        var p=(Map<?,?>)repository.prediction((String)run.get("runId"),29).get("response");
        assertEquals(false,p.get("valid"));assertNull(p.get("predicted_consumption_Ah"));
        assertEquals(EnergyV3Contract.MODEL,p.get("model_version"));
        verify(ai,never()).predictAirSimCapacity(anyLong(),anyList());
    }

    @Test
    void legacyFingerprintOmitsAbsentNewFieldsAndWrongSamplingIsRejected() throws Exception {
        var t=new TelemetryData();assertFalse(json.writeValueAsString(t).contains("velocityX"));
        assertThrows(com.coldaviation.exception.BusinessException.class,()->EnergyV3Contract.validate(
            Map.of("inference_method",EnergyV3Contract.MODEL,"sampling_contract","nearest_sample"),"nearest_sample"));
        assertThrows(com.coldaviation.exception.BusinessException.class,()->EnergyV3Contract.validate(
            Map.of("inference_method","unknown"),"test"));
    }

    @Test
    @SuppressWarnings("unchecked")
    void archivesInputsPredictionsLabelsAndDeduplicatesRetries() throws Exception {
        var run=createRun(60);fill(run,60);
        String id=(String)run.get("runId");
        assertEquals(31,calls.get());
        var detail=service.detail(id);
        var metrics=(Map<String,Object>)detail.get("metrics");
        assertEquals(31,((Number)metrics.get("valid_count")).intValue());
        assertEquals(21,((Number)metrics.get("verified_count")).intValue());
        assertEquals(0,((Number)metrics.get("mae_mah")).doubleValue(),1e-9);
        var original=repository.prediction(id,29);
        assertEquals(64,((String)original.get("inputSha256")).length());
        send(sample(run,29,29),200);
        assertEquals(31,calls.get());
        assertEquals(60,repository.run(id,false).getSampleCount());
        var conflict=sample(run,29,29);conflict.put("voltage",12);
        send(conflict,409);
        assertEquals(original,repository.prediction(id,29));
        service.finish(id,"COMPLETED",null);
        send(sample(run,29,29),200);
        assertEquals("COMPLETED",repository.run(id,false).getStatus());
    }

    @Test
    void gapStartsANewContinuousSuffixWithoutInterpolating() throws Exception {
        var run=createRun(45);
        for(int i=0;i<15;i++)send(sample(run,i,i),200);
        for(int i=15;i<44;i++)send(sample(run,i,i+1),200);
        assertEquals(0,calls.get());
        var p=(Map<?,?>)repository.prediction((String)run.get("runId"),43).get("response");
        assertEquals(29,((Number)p.get("window_samples")).intValue());
        assertTrue(p.get("reason").toString().contains("timestamp_gap"));
        send(sample(run,44,45),200);
        assertEquals(1,calls.get());
    }

    @Test
    void missingAndOutOfRangeFieldsAreArchivedAsUnavailable() throws Exception {
        var run=createRun(31);fill(run,29);
        var missing=sample(run,29,29);missing.remove("envTemperature");send(missing,200);
        var invalid=sample(run,30,30);invalid.put("batteryLevel",130);send(invalid,200);
        assertEquals(0,calls.get());
        var records=repository.events((String)run.get("runId"),28,10);
        assertTrue(((Map<?,?>)records.get(0).get("prediction")).get("reason").toString().contains("missing_field"));
        assertTrue(((Map<?,?>)records.get(1).get("prediction")).get("reason").toString().contains("out_of_range"));
    }

    @Test
    void rejectsOutOfOrderCrossRunAndClockMismatch() throws Exception {
        var run=createRun(10);send(sample(run,0,0),200);send(sample(run,5,5),200);
        send(sample(run,1,1),409);
        var wrong=sample(run,6,6);wrong.put("flightId","another_flight");send(wrong,400);
        var clock=sample(run,6,6);clock.put("collectTime",run.get("collectStartTime"));send(clock,400);
        assertEquals(2,repository.run((String)run.get("runId"),false).getSampleCount());
        mvc.perform(post("/api/runs/"+run.get("runId")+"/finish").contentType("application/json").content("{\"status\":\"COMPLETED\"}"))
            .andExpect(status().isConflict());
    }

    @Test
    void runsWithIdenticalFlightAndSourceTimeRemainIsolated() throws Exception {
        var a=createRun(30);var b=createRun(30);fill(a,20);fill(b,20);
        assertEquals(0,calls.get());
        for(int i=20;i<30;i++)send(sample(a,i,i),200);
        assertEquals(1,calls.get());
        assertEquals(20,repository.run((String)b.get("runId"),false).getSampleCount());
    }

    @Test
    void recheckIsAuditedWithoutOverwritingOriginalAndGuardsModelChanges() throws Exception {
        var run=createRun(30);fill(run,30);String id=(String)run.get("runId");
        var original=repository.prediction(id,29);
        assertEquals(true,service.recheck(id,29).get("consistent"));
        doReturn(prediction(.971,"d".repeat(64))).when(ai).predictCapacityRequest(anyMap());
        var changed=service.recheck(id,29);
        assertEquals(false,changed.get("consistent"));
        assertEquals("artifact_mismatch",changed.get("reason"));
        assertEquals(original,repository.prediction(id,29));
        assertEquals(2,repository.rechecks(id).size());
    }

    @Test
    void liveResetPreservesTelemetryPredictionsAndRuns() throws Exception {
        var run=createRun(30);fill(run,30);
        mvc.perform(post("/api/demo/reset")).andExpect(status().isOk()).andExpect(jsonPath("$.data.historyPreserved").value(true));
        assertEquals(30,repository.events((String)run.get("runId"),-1,100).size());
        assertEquals(30,repository.run((String)run.get("runId"),false).getSampleCount());
    }

    @Test
    void unavailableAiStillSavesTelemetryAndNeverInventsNumbers() throws Exception {
        var run=createRun(30);
        Map<String,Object> unavailable=new LinkedHashMap<>();
        unavailable.put("valid",false);unavailable.put("reason","ai_service_unavailable");
        unavailable.put("predicted_capacity_Ah",null);unavailable.put("predicted_consumption_Ah",null);
        doReturn(unavailable).when(ai).predictAirSimCapacity(anyLong(),anyList());
        fill(run,30);
        var response=(Map<?,?>)repository.prediction((String)run.get("runId"),29).get("response");
        assertEquals(false,response.get("valid"));assertNull(response.get("predicted_capacity_Ah"));
        assertEquals(30,repository.run((String)run.get("runId"),false).getSampleCount());
    }

    @Test
    void invalidRunMetadataIsRejectedBeforeCreatingRecords() throws Exception {
        mvc.perform(post("/api/runs").contentType("application/json").content("{}")).andExpect(status().isBadRequest());
    }
}
