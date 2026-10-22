from typing import Dict, Any, List
import pandas as pd
import numpy as np
import datetime
from typing import Dict, Any, List, Optional


# Thresholds for alerts (WHO Guidelines)
THRESHOLDS = {
    "pm2_5": {"warning": 15.0, "danger": 25.0, "unit": "µg/m³"},
    "pm10": {"warning": 45.0, "danger": 50.0, "unit": "µg/m³"},
    "no2": {"warning": 25.0, "danger": 50.0, "unit": "µg/m³"},
    "temp_max": {"warning": 33.0, "danger": 38.0, "unit": "°C"}
}

class DataProcessor:
    """
    Data Transformation, Calculations, and Alert Engine.
    Author: Student B (Data Analyst)
    """

    @staticmethod
    def process_raw_api_data(raw_data: Dict[str, Any]) -> pd.DataFrame:
        """Transforms raw API responses into a clean Pandas DataFrame."""
        w_hourly = raw_data.get("weather", {}).get("hourly", {})
        a_hourly = raw_data.get("air_quality", {}).get("hourly", {})

        df_weather = pd.DataFrame(w_hourly)
        df_air = pd.DataFrame(a_hourly)

        if df_weather.empty or df_air.empty:
            return pd.DataFrame()

        df = pd.merge(df_weather, df_air, on="time", how="inner")
        df["datetime"] = pd.to_datetime(df["time"])
        df.sort_values("datetime", inplace=True)
        return df

    @staticmethod
    def get_current_row(df: pd.DataFrame, utc_offset_seconds: Optional[int] = None) -> pd.Series:
        """
        Returns the measurement of the current hour: the last row that is not in the future.
        `utc_offset_seconds` is the city's offset to UTC (given by the API);
        if None (mock mode), the computer's local time is used.
        """
        if utc_offset_seconds is None:
            now = datetime.datetime.now()
        else:
            now = (datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                   + datetime.timedelta(seconds=utc_offset_seconds))

        past = df[df["datetime"] <= now]
        return past.iloc[-1] if not past.empty else df.iloc[0]

    @staticmethod
    def calculate_custom_health_index(df: pd.DataFrame) -> pd.Series:
        """
        Calculates a custom composite Comfort/Health Score (0-100 scale).
        Higher is better.
        """
        temp = df["temperature_2m"]
        humidity = df["relativehumidity_2m"]
        pm2_5 = df["pm2_5"]

        # Penalty factors based on optimal comfort conditions
        temp_penalty = np.abs(temp - 21.0) * 1.5
        humidity_penalty = np.abs(humidity - 50.0) * 0.3
        pollution_penalty = pm2_5 * 1.2

        score = 100 - (temp_penalty + humidity_penalty + pollution_penalty)
        return score.clip(0, 100).round(1)

    @staticmethod
    def detect_alerts(latest: pd.Series) -> List[Dict[str, str]]:
        """Checks one measurement row (the current hour) for threshold violations."""
        alerts = []

        # PM2.5 check
        if latest["pm2_5"] >= THRESHOLDS["pm2_5"]["danger"]:
            alerts.append({
                "level": "danger",
                "message": f"Alerte Rouge Pollution (PM2.5) : {latest['pm2_5']:.1f} {THRESHOLDS['pm2_5']['unit']} (Seuil: {THRESHOLDS['pm2_5']['danger']})"
            })
        elif latest["pm2_5"] >= THRESHOLDS["pm2_5"]["warning"]:
            alerts.append({
                "level": "warning",
                "message": f"Vigilance Pollution (PM2.5) : {latest['pm2_5']:.1f} {THRESHOLDS['pm2_5']['unit']}"
            })

        # NO2 check
        if latest["nitrogen_dioxide"] >= THRESHOLDS["no2"]["danger"]:
            alerts.append({
                "level": "danger",
                "message": f"Alerte Dépassement NO2 : {latest['nitrogen_dioxide']:.1f} µg/m³"
            })

        # Temperature check
        if latest["temperature_2m"] >= THRESHOLDS["temp_max"]["warning"]:
            alerts.append({
                "level": "warning",
                "message": f"Vigilance Forte Chaleur / Canicule : {latest['temperature_2m']:.1f} °C"
            })

        return alerts