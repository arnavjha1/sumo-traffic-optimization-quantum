import pandas as pd

INPUT_FILE = "data/Traffic_Hourly_Count_Seattle.csv"

def clean_number(value):
    """
    Converts values like '47,646' into 47646.
    Also handles blanks or invalid values safely.
    """
    if pd.isna(value):
        return None
    return int(str(value).replace(",", "").strip())

def calculate_hour_constants(csv_path):
    df = pd.read_csv(csv_path)

    # Clean numeric columns
    hour_cols = [f"HR{hour:02d}_TOTAL" for hour in range(1, 25)]
    numeric_cols = ["TOTAL"] + hour_cols

    for col in numeric_cols:
        df[col] = df[col].apply(clean_number)

    # Clean weekday and holiday columns
    df["WEEKDAY"] = df["WEEKDAY"].astype(int)
    df["HOLIDAY_YN"] = df["HOLIDAY_YN"].astype(str).str.strip()

    # Filter rows
    filtered = df[
        (df["TOTAL"] >= 10000) &
        (~df["WEEKDAY"].isin([6, 7])) &
        (df["HOLIDAY_YN"] == "N")
    ].copy()

    # Calculate hourly constants for each valid row
    for col in hour_cols:
        filtered[col + "_CONST"] = filtered[col] / filtered["TOTAL"]

    const_cols = [col + "_CONST" for col in hour_cols]

    # Average constants across all valid rows
    hour_constants = filtered[const_cols].mean().tolist()

    return hour_constants, filtered

if __name__ == "__main__":
    constants, filtered_rows = calculate_hour_constants(INPUT_FILE)

    print("Number of valid rows:", len(filtered_rows))
    print("24 hourly constants:")
    print(constants)
    print("Valid rows:")
    print(len(filtered_rows))