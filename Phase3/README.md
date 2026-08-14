# 寒域智航 Phase 3：容量预测接口

## 启动服务

在项目根目录执行：

```bash
.venv/bin/uvicorn Phase3.inference_api:app --host 127.0.0.1 --port 8000
```

启动后可访问：

- 健康检查：`http://127.0.0.1:8000/health`
- 交互式接口文档：`http://127.0.0.1:8000/docs`

## 预测接口

请求地址：`POST /predict`

请求体必须包含连续 10 个循环的数据。每个循环包含原始温度、风速、电压、电流和 SOC，接口会自动使用 `Phase1/scaler.pkl` 对前四项特征进行标准化。

```json
{
  "cycles": [
    {
      "temperature_C": -27.0,
      "wind_speed_ms": 3.0,
      "voltage_V": 16.5,
      "current_A": 8.0,
      "soc_pct": 95.0
    }
  ]
}
```

示例中的周期对象需要重复提供 10 个。返回结果包含下一循环预测容量、实际推理耗时、输入周期数和模型版本。

## 当前用途

该接口是本地推理原型，加载 `Phase1/multi_lstm_model_quantized.pth`。当前模型使用 NASA 电池容量数据与模拟环境特征训练，接口结果仅用于技术流程验证，不能作为真实无人机的安全决策依据。

## 接口基准测试

保持服务运行，并在另一个终端执行：

```bash
.venv/bin/python Phase3/benchmark_api.py
```

脚本会从四块电池的测试区间各选取 5 组样本，向接口发送共 20 次请求，并生成逐请求结果和中文测试报告。
