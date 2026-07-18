import os

import pandas as pd
import scipy.io as sio


FILE_MAP = {
    "B5Capacity.mat": "B5_capacity.csv",
    "B6Capacity.mat": "B6_capacity.csv",
    "B7Capacity.mat": "B7_capacity.csv",
    "B18Capacity.mat": "B18_capacity.csv",
}


def extract_capacity(mat_data):
    """Extract the capacity array from loaded MATLAB data."""
    for variable_name, variable_value in mat_data.items():
        if not variable_name.startswith("__"):
            return variable_value.flatten()
    raise ValueError("No capacity data found")


def export_single_file(input_file_path, output_file_path):
    """Read one .mat file and export cycle-capacity data to CSV."""
    mat_data = sio.loadmat(input_file_path)
    capacity_array = extract_capacity(mat_data)

    data_frame = pd.DataFrame(
        {
            "cycle": range(1, len(capacity_array) + 1),
            "capacity_Ah": capacity_array,
        }
    )
    data_frame.to_csv(output_file_path, index=False)

    return len(data_frame)


def main():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    learn_dir = os.path.dirname(current_dir)
    data_dir = os.path.join(learn_dir, "NasaBatteryTest")
    output_dir = os.path.join(current_dir, "NASA_CSV")
    os.makedirs(output_dir, exist_ok=True)

    total_rows = 0
    for input_file_name, output_file_name in FILE_MAP.items():
        input_file_path = os.path.join(data_dir, input_file_name)
        output_file_path = os.path.join(output_dir, output_file_name)

        row_count = export_single_file(input_file_path, output_file_path)
        total_rows += row_count
        print(f"已保存 {output_file_name}，共 {row_count} 行数据")

    print(f"全部导出完成，共计 {total_rows} 组数据")


if __name__ == "__main__":
    main()
