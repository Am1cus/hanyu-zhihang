import json
import os
import time
import urllib.error
import urllib.request

import joblib
import numpy as np
import pandas as pd


LOOKBACK = 10
TRAIN_RATIO = 0.8
SAMPLES_PER_BATTERY = 5
REQUEST_TIMEOUT_SECONDS = 5
BATTERY_ORDER = ["B5", "B6", "B7", "B18"]
STANDARDIZED_FEATURE_COLUMNS = [
    "temperature_C",
    "wind_speed_ms",
    "voltage_V",
    "current_A",
]
FEATURE_COLUMNS = STANDARDIZED_FEATURE_COLUMNS + ["soc_pct"]


def build_test_cases(data_frame, scaler):
    test_cases = []

    for battery_id in BATTERY_ORDER:
        battery_data = (
            data_frame[data_frame["battery_id"] == battery_id]
            .sort_values("cycle")
            .reset_index(drop=True)
        )
        split_index = int(len(battery_data) * TRAIN_RATIO)
        target_indexes = range(split_index, split_index + SAMPLES_PER_BATTERY)

        for target_index in target_indexes:
            feature_window = battery_data.iloc[target_index - LOOKBACK : target_index]
            standardized_values = feature_window[STANDARDIZED_FEATURE_COLUMNS]
            raw_values = scaler.inverse_transform(standardized_values)

            cycles = []
            for row_index, (_, row) in enumerate(feature_window.iterrows()):
                cycles.append(
                    {
                        "temperature_C": float(raw_values[row_index, 0]),
                        "wind_speed_ms": float(raw_values[row_index, 1]),
                        "voltage_V": float(raw_values[row_index, 2]),
                        "current_A": float(raw_values[row_index, 3]),
                        "soc_pct": float(row["soc_pct"]),
                    }
                )

            target_row = battery_data.iloc[target_index]
            test_cases.append(
                {
                    "battery_id": battery_id,
                    "cycle": int(target_row["cycle"]),
                    "true_capacity_Ah": float(target_row["capacity_Ah"]),
                    "payload": {"cycles": cycles},
                }
            )

    return test_cases


def send_prediction_request(api_url, payload):
    request = urllib.request.Request(
        f"{api_url}/predict",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    start_time = time.perf_counter()
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        response_body = json.loads(response.read().decode("utf-8"))
    request_time_ms = (time.perf_counter() - start_time) * 1000

    return response.status, response_body, request_time_ms


def run_benchmark(test_cases, api_url):
    result_rows = []

    for case_index, test_case in enumerate(test_cases, start=1):
        try:
            status_code, response_body, request_time_ms = send_prediction_request(
                api_url,
                test_case["payload"],
            )
            predicted_capacity = float(response_body["predicted_capacity_Ah"])
            absolute_percentage_error = (
                abs(predicted_capacity - test_case["true_capacity_Ah"])
                / test_case["true_capacity_Ah"]
                * 100
            )
            error_message = ""
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as error:
            status_code = 0
            predicted_capacity = np.nan
            absolute_percentage_error = np.nan
            request_time_ms = np.nan
            error_message = str(error)

        result_rows.append(
            {
                "request_id": case_index,
                "battery_id": test_case["battery_id"],
                "cycle": test_case["cycle"],
                "true_capacity_Ah": test_case["true_capacity_Ah"],
                "predicted_capacity_Ah": predicted_capacity,
                "absolute_percentage_error_pct": absolute_percentage_error,
                "request_time_ms": request_time_ms,
                "status_code": status_code,
                "error_message": error_message,
            }
        )

    return pd.DataFrame(result_rows)


def calculate_summary(results_frame):
    successful_results = results_frame[results_frame["status_code"] == 200]
    total_requests = len(results_frame)
    successful_requests = len(successful_results)

    if successful_results.empty:
        return {
            "total_requests": total_requests,
            "successful_requests": 0,
            "success_rate_pct": 0.0,
            "average_time_ms": np.nan,
            "p95_time_ms": np.nan,
            "p99_time_ms": np.nan,
            "mape_pct": np.nan,
        }

    return {
        "total_requests": total_requests,
        "successful_requests": successful_requests,
        "success_rate_pct": successful_requests / total_requests * 100,
        "average_time_ms": successful_results["request_time_ms"].mean(),
        "p95_time_ms": successful_results["request_time_ms"].quantile(0.95),
        "p99_time_ms": successful_results["request_time_ms"].quantile(0.99),
        "mape_pct": successful_results["absolute_percentage_error_pct"].mean(),
    }


def print_summary(summary):
    print("=" * 58)
    print("容量预测接口基准测试结果：")
    print(f"请求总数：{summary['total_requests']}")
    print(f"成功请求：{summary['successful_requests']}")
    print(f"成功率：{summary['success_rate_pct']:.2f}%")
    print(f"平均响应时间：{summary['average_time_ms']:.4f} ms")
    print(f"P95 响应时间：{summary['p95_time_ms']:.4f} ms")
    print(f"P99 响应时间：{summary['p99_time_ms']:.4f} ms")
    print(f"MAPE：{summary['mape_pct']:.4f}%")
    print("=" * 58)


def save_report(report_path, summary, api_url):
    average_latency_passed = summary["average_time_ms"] <= 150
    report_content = f"""# 寒域智航容量预测接口基准测试报告

## 测试说明

- 接口地址：`{api_url}/predict`
- 测试样本：B5、B6、B7、B18 各 5 组，共 {summary['total_requests']} 组
- 每组输入：连续 10 个循环的温度、风速、电压、电流和 SOC
- 测试范围：各电池后 20% 测试区间，不使用训练区间样本

## 测试结果

| 指标 | 结果 |
| --- | ---: |
| 请求总数 | {summary['total_requests']} |
| 成功请求数 | {summary['successful_requests']} |
| 成功率 | {summary['success_rate_pct']:.2f}% |
| 平均响应时间 | {summary['average_time_ms']:.4f} ms |
| P95 响应时间 | {summary['p95_time_ms']:.4f} ms |
| P99 响应时间 | {summary['p99_time_ms']:.4f} ms |
| 容量预测 MAPE | {summary['mape_pct']:.4f}% |

## 验收结论

平均响应时间目标为不超过 150 ms。本次测试{'通过' if average_latency_passed else '未通过'}该目标。

本结果基于本地 macOS CPU 环境和模拟环境特征，仅用于接口原型验证；真实部署性能需要在目标设备和真实飞行数据上重新测试。
"""

    with open(report_path, "w", encoding="utf-8") as report_file:
        report_file.write(report_content)


def main():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(current_dir)
    phase1_dir = os.path.join(project_dir, "Phase1")
    dataset_path = os.path.join(phase1_dir, "training_dataset_v1.csv")
    scaler_path = os.path.join(phase1_dir, "scaler.pkl")
    results_path = os.path.join(current_dir, "api_benchmark_results.csv")
    report_path = os.path.join(current_dir, "api_benchmark_report.md")
    api_url = os.environ.get("HANYU_API_URL", "http://127.0.0.1:8000").rstrip("/")

    data_frame = pd.read_csv(dataset_path, encoding="utf-8-sig")
    scaler = joblib.load(scaler_path)
    test_cases = build_test_cases(data_frame, scaler)
    results_frame = run_benchmark(test_cases, api_url)
    summary = calculate_summary(results_frame)

    results_frame.to_csv(results_path, index=False, encoding="utf-8-sig")
    save_report(report_path, summary, api_url)
    print_summary(summary)
    print(f"逐请求结果已保存：{results_path}")
    print(f"基准测试报告已保存：{report_path}")

    if summary["successful_requests"] != summary["total_requests"]:
        raise RuntimeError("存在接口请求失败，请检查服务状态和结果文件")


if __name__ == "__main__":
    main()
