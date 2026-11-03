"""Load the UCI Seoul bike-sharing data and add the columns the models use."""

from pathlib import Path

import numpy as np
import pandas as pd

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "SeoulBikeData.csv"

COLUMNS = {
    "Date": "date",
    "Rented Bike Count": "count",
    "Hour": "hour",
    "Temperature(°C)": "temp",
    "Humidity(%)": "humidity",
    "Wind speed (m/s)": "wind",
    "Visibility (10m)": "visibility",
    "Dew point temperature(°C)": "dew",
    "Solar Radiation (MJ/m2)": "solar",
    "Rainfall(mm)": "rain",
    "Snowfall (cm)": "snow",
    "Seasons": "season",
    "Holiday": "holiday",
    "Functioning Day": "functioning",
}


def load_data(path: str | Path | None = None) -> pd.DataFrame:
    """Return all 8,760 raw hours, with a timestamp and model-ready flags.

    ``operating`` is False for the 295 hours the rental system was closed.
    Those rows are kept because the time-series baseline needs a continuous
    hourly clock; count models filter them out.
    """
    df = pd.read_csv(path or DATA_PATH, encoding="latin1").rename(columns=COLUMNS)
    missing = set(COLUMNS.values()) - set(df.columns)
    if missing:
        raise ValueError(f"dataset is missing columns: {sorted(missing)}")

    df["date"] = pd.to_datetime(df["date"], dayfirst=True)
    df["timestamp"] = df["date"] + pd.to_timedelta(df["hour"], unit="h")
    if df["timestamp"].duplicated().any():
        raise ValueError("dataset has duplicate date/hour rows")

    df["operating"] = df["functioning"].eq("Yes")
    df["weekend"] = (df["date"].dt.day_of_week >= 5).astype(int)
    df["holiday_flag"] = df["holiday"].eq("Holiday").astype(int)
    df["log_solar"] = np.log1p(df["solar"])
    df["log_rain"] = np.log1p(df["rain"])
    return df.sort_values("timestamp").reset_index(drop=True)
