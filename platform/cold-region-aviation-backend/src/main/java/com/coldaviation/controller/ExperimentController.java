package com.coldaviation.controller;

import com.coldaviation.common.Result;
import com.coldaviation.repository.ExperimentRepository;
import com.coldaviation.service.ExperimentService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.*;
import java.util.*;

@RestController
@RequestMapping("/api/runs")
public class ExperimentController {
    private final ExperimentRepository repository;
    private final ExperimentService service;
    public ExperimentController(ExperimentRepository repository, ExperimentService service) { this.repository=repository;this.service=service; }

    @PostMapping
    public Result<?> create(@Valid @RequestBody ExperimentService.CreateRun input) { return Result.success(service.create(input)); }

    @GetMapping
    public Result<?> list(@RequestParam(defaultValue="1") int page, @RequestParam(defaultValue="10") int size,
                          @RequestParam(required=false) String flightId) {
        if(page<1 || size<1 || size>100) throw new IllegalArgumentException("页码或页大小超出范围");
        return Result.success(repository.list(page,size,flightId));
    }

    @GetMapping("/{id}")
    public Result<?> detail(@PathVariable String id) { return Result.success(service.detail(id)); }

    @GetMapping("/{id}/events")
    public Result<?> events(@PathVariable String id,@RequestParam(defaultValue="-1") int afterSeq,
                            @RequestParam(defaultValue="1000") int limit) {
        if(afterSeq< -1 || limit<1 || limit>1000) throw new IllegalArgumentException("分页范围无效");
        repository.run(id,false);
        return Result.success(repository.events(id,afterSeq,limit));
    }

    public record FinishRun(String status,String error) {}

    @PostMapping("/{id}/finish")
    public Result<?> finish(@PathVariable String id,@RequestBody FinishRun request) {
        return Result.success(service.finish(id,request.status(),request.error()));
    }

    @PostMapping("/{id}/recheck")
    public Result<?> recheck(@PathVariable String id,@RequestParam int sampleSeq) {
        if(sampleSeq<0) throw new IllegalArgumentException("sampleSeq不能为负");
        return Result.success(service.recheck(id,sampleSeq));
    }

    @GetMapping("/{id}/rechecks")
    public Result<?> rechecks(@PathVariable String id) {
        repository.run(id,false);
        return Result.success(repository.rechecks(id));
    }
}
