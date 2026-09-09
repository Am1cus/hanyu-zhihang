package com.coldaviation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * 寒域智航 - 无人机动力预测与AI预警云端协同调度系统
 * 主启动类
 */
@SpringBootApplication
@EnableScheduling
public class ColdAviationApplication {

    public static void main(String[] args) {
        SpringApplication.run(ColdAviationApplication.class, args);
        System.out.println("============================================");
        System.out.println("  寒域智航 后端服务启动成功!");
        System.out.println("  Cold Region Aviation Backend Started!");
        System.out.println("============================================");
    }
}
