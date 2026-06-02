import subprocess
import pandas as pd
import numpy as np
from pathlib import Path

# Paths
BASE_DIR = Path("data_analysis")
ALPHA_SCRIPT = BASE_DIR / "calc_alpha.py"
TRAFFIC_SCRIPT = BASE_DIR / "calc_traffic_over_time.py"
ALPHA_SUMMARY_CSV = BASE_DIR / "generated_data" / "alpha_citywide_summary.csv"
HOURLY_CONSTANTS_CSV = BASE_DIR / "generated_data" / "calculated_hourly_constants.csv"

# 1. Run both scripts and wait for completion
subprocess.run(["python", str(ALPHA_SCRIPT)], check=True)
subprocess.run(["python", str(TRAFFIC_SCRIPT)], check=True)

# 2. Load outputs
alpha_summary = pd.read_csv(ALPHA_SUMMARY_CSV)
hourly_constants = pd.read_csv(HOURLY_CONSTANTS_CSV)

# 3. Extract needed values
alpha_straight = alpha_summary["mean_alpha_straight"].iloc[0]
alpha_left = alpha_summary["mean_alpha_left"].iloc[0]
alpha_right = alpha_summary["mean_alpha_right"].iloc[0]
departure_constant = alpha_left + alpha_right

hour_constant_list = hourly_constants["hour_constant"].tolist()
average_hour_traffic_list = hourly_constants["average_hourly_traffic"].tolist()

# 4. Build 24x4 array: [average_hour_traffic, hour_constant, alpha_straight, departure_constant]
data_array = np.zeros((24, 3))

for i in range(24):
    data_array[i, 0] = average_hour_traffic_list[i] * hour_constant_list[i] * 24
    data_array[i, 1] = alpha_straight
    data_array[i, 2] = departure_constant

# Optional: convert to pandas DataFrame for easier inspection
df_24x3 = pd.DataFrame(
    data_array,
    columns=["hourly_rate", "alpha_straight", "departure_constant"]
)

print(df_24x3)