"""Predict minutes directly, or compute the example round-trip route."""
import argparse
import json

from .contracts import PredictionInput, RouteInput
from .model import EnduranceModel
from .routes import plan_round_trip


def main():
    parser = argparse.ArgumentParser(description="输入温度、电量和风速，预测预计可飞分钟数")
    parser.add_argument("--temperature", type=float, default=-20, help="摄氏度")
    parser.add_argument("--battery", type=float, default=80, help="当前电量百分比，0 到 100")
    parser.add_argument("--wind", type=float, default=5, help="风速 m/s")
    parser.add_argument("--speed", type=float, default=2, help="平飞地速 m/s")
    parser.add_argument("--reserve", type=float, default=20, help="预留电量百分比")
    parser.add_argument("--capacity", type=float, help="室温额定容量 Ah；默认使用拟合机型")
    parser.add_argument("--route", action="store_true", help="同时规划示例地图的省电往返路线")
    args = parser.parse_args()
    values = dict(temperature_c=args.temperature, battery_percent=args.battery, wind_speed_ms=args.wind,
                  ground_speed_ms=args.speed, reserve_percent=args.reserve, nominal_capacity_ah=args.capacity)
    try:
        result = plan_round_trip(RouteInput(**values)) if args.route else EnduranceModel().predict_input(PredictionInput(**values))
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
