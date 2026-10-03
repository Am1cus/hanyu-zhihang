"""Extract numerical polyline coordinates from the manufacturer's original PDF.

Run with a Python containing pdfplumber. No curve fitting or hand-made values.
The original document remains outside the source repository.
"""
import argparse
import hashlib
import json
from pathlib import Path

import pdfplumber

URL = "https://www.molicel.com/cn/wp-content/uploads/INR21700P42A_1.7_Product-Data-Sheet-of-INR-21700-P42A-80092.pdf"


def extract(pdf_path, output):
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        # Axes are original vector lines in the temperature plot, PDF points.
        x0, x1 = 378.025497991125, 553.90370618475
        y0, y1 = 521.1674739277896, 403.599516232386
        colors = {-20: (0.0, 0.8, 1.0), 0: (1.0, 0.0, 1.0), 23: (0.0, 0.0, 1.0)}
        curves = []
        for temperature, color in colors.items():
            candidates = [c for c in page.curves if c.get("stroking_color") == color
                          and 400 < c["top"] < 430 and 460 < c["bottom"] < 465
                          and c["x0"] > 370 and len(c["pts"]) > 100]
            if len(candidates) != 1:
                raise ValueError(f"Expected one vector curve for {temperature}C: {len(candidates)}")
            curve = candidates[0]
            points = []
            for x, y in curve["pts"]:
                q = (x-x0)/(x1-x0)*4.4  # capacity axis: 0..4400mAh
                v = (y0-y)/(y0-y1)*5.0  # voltage axis: 0..5V
                point = {"capacity_ah": round(q, 8), "voltage_v": round(v, 8)}
                if points and point["capacity_ah"] <= points[-1]["capacity_ah"]:
                    raise ValueError("Non-increasing original polyline")
                points.append(point)
            energy = sum((b["capacity_ah"]-a["capacity_ah"])
                         *(a["voltage_v"]+b["voltage_v"])/2 for a,b in zip(points, points[1:]))
            curves.append({"temperature_c": temperature, "points": points,
                           "cell_energy_wh": round(energy, 8),
                           "endpoint_capacity_ah": points[-1]["capacity_ah"],
                           "extracted_point_count": len(points),
                           "original_vector_bbox_pdf_pt": [curve[k] for k in ("x0","top","x1","bottom")]})
        data = {
            "schema_version": 1,
            "source": {
                "title": "Molicel INR-21700-P42A Product Data Sheet version 1.7",
                "url": URL,
                "sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
                "page": 1,
                "digitization_method": "Original PDF vector polylines and axis calibration; no fitting, smoothing, or invented temperature coefficients",
                "axes_pdf_pt": {"capacity_zero_x": x0, "capacity_4_4ah_x": x1,
                                 "voltage_zero_y": y0, "voltage_5v_y": y1},
                "charge_conditions": "CC-CV 4.2A to 4.2V, 50mA cut at 23C",
                "discharge_conditions": "4.2A constant current, 2.5V cutoff",
                "limitation": "Reference curves, not performance guarantee. Endpoint voltage differs slightly from 2.5V because plotted vector coordinates are approximate. No real aircraft calibration.",
            },
            "discharge_current_a": 4.2,
            "series_cells": 4,
            "parallel_cells": 1,
            "reference_temperature_c": 23,
            "interpolation": "Piecewise linear voltage versus discharged Ah; interpolate temperature voltage on union normalized capacity nodes, then integrate energy; never extrapolate temperature",
            "temperature_scope_c": [-20, 23],
            "curves": curves,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        print(json.dumps({"output": str(output), "source_sha256": data["source"]["sha256"],
                          "curves": [{k:c[k] for k in ("temperature_c", "cell_energy_wh", "endpoint_capacity_ah", "extracted_point_count")} for c in curves]}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    extract(args.pdf, args.output)
