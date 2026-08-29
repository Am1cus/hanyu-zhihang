"""AirSim未来剩余容量LSTM结构与特征定义。"""

from torch import nn


LOOKBACK = 30
FORECAST_HORIZON_SECONDS = 10
FEATURE_COLUMNS = [
    "env_temperature_C",
    "wind_speed_ms",
    "voltage_V",
    "current_A",
    "battery_level_pct",
    "speed_ms",
    "altitude_m",
]


class AirSimCapacityLSTM(nn.Module):
    def __init__(self, input_size=len(FEATURE_COLUMNS), hidden_size=64, num_layers=2, dropout=0.2):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout,
        )
        self.output_layer = nn.Linear(hidden_size, 1)

    def forward(self, inputs):
        output, _ = self.lstm(inputs)
        return self.output_layer(output[:, -1, :])
