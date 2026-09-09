
CREATE TABLE IF NOT EXISTS drone (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    drone_code VARCHAR(50) NOT NULL UNIQUE,
    drone_name VARCHAR(100) NOT NULL,
    model VARCHAR(100), manufacturer VARCHAR(100),
    max_payload DOUBLE, max_range DOUBLE, max_speed DOUBLE,
    status INT DEFAULT 0,
    latitude DOUBLE, longitude DOUBLE, altitude DOUBLE, battery_level DOUBLE,
    remark VARCHAR(500),
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted INT DEFAULT 0
);

CREATE TABLE IF NOT EXISTS telemetry_data (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    drone_id BIGINT NOT NULL, drone_code VARCHAR(50) NOT NULL,
    latitude DOUBLE, longitude DOUBLE, altitude DOUBLE, speed DOUBLE, heading DOUBLE,
    voltage DOUBLE, current DOUBLE, battery_level DOUBLE, remaining_capacity_ah DOUBLE,
    battery_temperature DOUBLE, env_temperature DOUBLE,
    wind_speed DOUBLE, wind_direction DOUBLE, humidity DOUBLE, signal_strength INT,
    collect_time TIMESTAMP NOT NULL, create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS battery_status (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    drone_id BIGINT NOT NULL, drone_code VARCHAR(50) NOT NULL, battery_code VARCHAR(50),
    health_score DOUBLE, current_level DOUBLE, current_voltage DOUBLE,
    internal_resistance DOUBLE, temperature DOUBLE, cycle_count INT,
    nominal_capacity INT, available_capacity INT,
    predicted_range DOUBLE, predicted_flight_time DOUBLE, capacity_decay_rate DOUBLE,
    assess_temperature DOUBLE, assess_time TIMESTAMP,
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS warning_record (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    drone_id BIGINT NOT NULL, drone_code VARCHAR(50) NOT NULL,
    warning_type VARCHAR(20) NOT NULL, warning_level INT NOT NULL,
    title VARCHAR(200) NOT NULL, message CLOB,
    trigger_temperature DOUBLE, trigger_battery_level DOUBLE, trigger_wind_speed DOUBLE,
    trigger_latitude DOUBLE, trigger_longitude DOUBLE,
    handle_status INT DEFAULT 0, handle_result VARCHAR(500), handle_time TIMESTAMP,
    warning_time TIMESTAMP NOT NULL, create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS flight_plan (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    drone_id BIGINT NOT NULL, drone_code VARCHAR(50) NOT NULL,
    plan_name VARCHAR(200) NOT NULL, description VARCHAR(500),
    start_latitude DOUBLE, start_longitude DOUBLE, end_latitude DOUBLE, end_longitude DOUBLE,
    waypoints CLOB, plan_altitude DOUBLE, plan_speed DOUBLE,
    estimated_distance DOUBLE, estimated_time DOUBLE, estimated_energy DOUBLE,
    algorithm_type VARCHAR(20) DEFAULT 'ASTAR',
    plan_temperature DOUBLE, plan_wind_speed DOUBLE, status INT DEFAULT 0,
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


INSERT INTO drone (id, drone_code, drone_name, model, manufacturer, status, remark)
SELECT 2, 'AIRSIM-001', 'AirSim仿真无人机', 'AirSim Multirotor', 'Microsoft AirSim', 1, '仿真数据源，不代表真机'
WHERE NOT EXISTS (SELECT 1 FROM drone WHERE id = 2 OR drone_code = 'AIRSIM-001');

ALTER TABLE telemetry_data ADD COLUMN IF NOT EXISTS run_id VARCHAR(36);
ALTER TABLE telemetry_data ADD COLUMN IF NOT EXISTS flight_id VARCHAR(100);
ALTER TABLE telemetry_data ADD COLUMN IF NOT EXISTS sample_seq INT;
ALTER TABLE telemetry_data ADD COLUMN IF NOT EXISTS source_time_s DOUBLE;
ALTER TABLE telemetry_data ADD COLUMN IF NOT EXISTS payload_sha256 VARCHAR(64);
ALTER TABLE telemetry_data ADD COLUMN IF NOT EXISTS velocity_x DOUBLE;
ALTER TABLE telemetry_data ADD COLUMN IF NOT EXISTS velocity_y DOUBLE;
ALTER TABLE telemetry_data ADD COLUMN IF NOT EXISTS velocity_z DOUBLE;
ALTER TABLE telemetry_data ADD COLUMN IF NOT EXISTS wind_x DOUBLE;
ALTER TABLE telemetry_data ADD COLUMN IF NOT EXISTS wind_y DOUBLE;
ALTER TABLE telemetry_data ADD COLUMN IF NOT EXISTS wind_z DOUBLE;
ALTER TABLE warning_record ADD COLUMN IF NOT EXISTS run_id VARCHAR(36);
ALTER TABLE warning_record ADD COLUMN IF NOT EXISTS flight_id VARCHAR(100);
CREATE UNIQUE INDEX IF NOT EXISTS ux_telemetry_run_seq ON telemetry_data(run_id, sample_seq);

CREATE TABLE IF NOT EXISTS experiment_run (
 run_id VARCHAR(36) PRIMARY KEY, flight_id VARCHAR(100) NOT NULL,
 drone_id BIGINT NOT NULL, drone_code VARCHAR(50) NOT NULL,
 data_source VARCHAR(40) NOT NULL, source_label VARCHAR(300) NOT NULL,
 source_sha256 VARCHAR(64) NOT NULL, config_sha256 VARCHAR(64) NOT NULL,
 preprocessing_version VARCHAR(100) NOT NULL, config_json CLOB NOT NULL,
 expected_samples INT NOT NULL, sample_count INT NOT NULL DEFAULT 0,
 status VARCHAR(20) NOT NULL DEFAULT 'RUNNING', last_error VARCHAR(500),
 collect_start_time TIMESTAMP NOT NULL, created_at TIMESTAMP NOT NULL, finished_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS prediction_record (
 telemetry_id BIGINT PRIMARY KEY, run_id VARCHAR(36) NOT NULL, sample_seq INT NOT NULL,
 source_time_s DOUBLE NOT NULL, target_source_time_s DOUBLE NOT NULL,
 valid BOOLEAN NOT NULL, reason VARCHAR(1000),
 window_start_seq INT, window_end_seq INT, input_sha256 VARCHAR(64),
 request_json CLOB NOT NULL, response_json CLOB NOT NULL, event_json CLOB NOT NULL,
 model_version VARCHAR(100), model_sha256 VARCHAR(64), scaler_sha256 VARCHAR(64),
 current_capacity_ah DOUBLE, predicted_consumption_ah DOUBLE, predicted_capacity_ah DOUBLE,
 actual_consumption_ah DOUBLE, absolute_error_ah DOUBLE, percentage_error DOUBLE,
 label_status VARCHAR(30) NOT NULL DEFAULT 'pending', created_at TIMESTAMP NOT NULL,
 UNIQUE (run_id, sample_seq)
);
CREATE INDEX IF NOT EXISTS ix_prediction_target ON prediction_record(run_id, target_source_time_s);
CREATE TABLE IF NOT EXISTS prediction_recheck (
 recheck_id VARCHAR(36) PRIMARY KEY, run_id VARCHAR(36) NOT NULL, sample_seq INT NOT NULL,
 report_json CLOB NOT NULL, created_at TIMESTAMP NOT NULL
);
