from pathlib import Path
import pandas as pd

INPUT_FILE = Path(__file__).resolve().parents[1] / "data" / "Traffic_Count_Studies_by_Hour.csv"

OUTPUT_FILE = (
    Path(__file__).resolve().parent
    / "generated_data"
    / "calculated_hourly_constants.csv"
)

def clean_number(value):
    if pd.isna(value):
        return None
    return int(str(value).replace(",", "").strip())

def calculate_hour_constants(csv_path):
    df = pd.read_csv(csv_path)

    hour_cols = [f"HR{hour:02d}_TOTAL" for hour in range(1, 25)]
    numeric_cols = ["TOTAL"] + hour_cols
    required_cols = numeric_cols + ["WEEKDAY", "HOLIDAY_YN"]

    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(
            f"Missing required columns in {csv_path}: {missing_cols}. "
            f"Available columns: {list(df.columns)}"
        )

    # Clean numeric columns
    for col in numeric_cols:
        df[col] = df[col].apply(clean_number)

    df["WEEKDAY"] = df["WEEKDAY"].astype(int)
    df["HOLIDAY_YN"] = df["HOLIDAY_YN"].astype(str).str.strip()

    # Filter rows
    filtered = df[
        (df["TOTAL"] >= 10000)
        & (~df["WEEKDAY"].isin([6, 7]))
        & (df["HOLIDAY_YN"] == "N")
    ].copy()

    # Calculate hourly constants
    for col in hour_cols:
        filtered[col + "_CONST"] = filtered[col] / filtered["TOTAL"]

    const_cols = [col + "_CONST" for col in hour_cols]
    hour_constants = filtered[const_cols].mean().tolist()

    # ----------------------------
    # Calculate average traffic per hour
    # ----------------------------
    total_volume_per_row = filtered["TOTAL"].sum()
    num_rows = len(filtered)
    average_hourly_traffic = total_volume_per_row / (num_rows * 24)

    # ----------------------------
    # Write CSV
    # ----------------------------
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    output_df = pd.DataFrame({
        "hour": list(range(1, 25)),
        "hour_constant": hour_constants,
        "average_hourly_traffic": [average_hourly_traffic] * 24
    })

    output_df.to_csv(OUTPUT_FILE, index=False)

    return hour_constants, filtered, average_hourly_traffic

if __name__ == "__main__":
    constants, filtered_rows, avg_traffic = calculate_hour_constants(INPUT_FILE)

    print("Number of valid rows:", len(filtered_rows))
    print("24 hourly constants:")
    print(constants)
    print("Average traffic per hour (across all valid rows):")
    print(avg_traffic)
    print("Valid rows:")
    print(len(filtered_rows))
    print(f"Saved hourly constants CSV to: {OUTPUT_FILE}")