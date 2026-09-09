package com.coldaviation.entity;

import lombok.Data;
import java.time.LocalDateTime;

@Data
public class ExperimentRun {
    private String runId;
    private String flightId;
    private Long droneId;
    private String droneCode;
    private String dataSource;
    private String sourceLabel;
    private String sourceSha256;
    private String configSha256;
    private String preprocessingVersion;
    private String configJson;
    private Integer expectedSamples;
    private Integer sampleCount;
    private String status;
    private String lastError;
    private LocalDateTime collectStartTime;
    private LocalDateTime createdAt;
    private LocalDateTime finishedAt;
}
