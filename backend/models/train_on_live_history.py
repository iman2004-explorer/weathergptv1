"""
Retrains the WeatherGPT Risk Index on REAL historical daily weather
observations (not synthetic data), pulled from Open-Meteo's free
historical archive for a spread of Indian cities across multiple years.

Requires internet access. Run with:

    python train_on_live_history.py

This overwrites weather_risk_model.pkl / model_meta.json with a model
trained on real observed data, using the exact same feature schema, so the
backend needs no code changes to use it.
"""
import json
import time
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import joblib

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FEATURES = ["month", "latitude", "temp_max", "temp_min", "humidity", "precip_prob", "wind_max", "uv_max"]
LABELS = ["low", "moderate", "high", "severe"]

# A spread of Indian cities across climate zones/latitudes.
CITIES = [
    ("Delhi", 28.61, 77.21), ("Mumbai", 19.08, 72.88), ("Kolkata", 22.57, 88.36),
    ("Chennai", 13.08, 80.27), ("Bengaluru", 12.97, 77.59), ("Hyderabad", 17.39, 78.49),
    ("Jaipur", 26.91, 75.79), ("Guwahati", 26.14, 91.74), ("Bhopal", 23.26, 77.41),
    ("Thiruvananthapuram", 8.52, 76.94), ("Srinagar", 34.08, 74.79), ("Patna", 25.59, 85.14),
    ("Ahmedabad", 23.02, 72.57), ("Nagpur", 21.15, 79.09), ("Chandigarh", 30.73, 76.78),
]

START_DATE = "2019-01-01"
END_DATE = "2024-12-31"


def label_from_row(temp_max, temp_min, precip_sum, wind_max, uv_max):
    """Domain rule used only to LABEL real historical rows (features are
    the real observations; only the risk category is rule-derived, since
    IMD-grade hazard-severity ground truth isn't in the free API)."""
    precip_prob_proxy = min(100, precip_sum * 12)  # rough proxy from mm -> risk scale
    score = 0
    score += 2 if precip_prob_proxy >= 75 else (1 if precip_prob_proxy >= 55 else 0)
    score += 2 if temp_max >= 42 else (1 if temp_max >= 38 else 0)
    score += 1 if temp_min <= 4 else 0
    score += 2 if wind_max >= 45 else (1 if wind_max >= 30 else 0)
    score += 1 if uv_max >= 9 else 0
    if score < 1.2:
        return 0, precip_prob_proxy
    if score < 2.6:
        return 1, precip_prob_proxy
    if score < 4.2:
        return 2, precip_prob_proxy
    return 3, precip_prob_proxy


def fetch_city_history(name, lat, lon):
    print(f"Fetching {name}...")
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": START_DATE, "end_date": END_DATE,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,uv_index_max,relative_humidity_2m_mean",
        "timezone": "auto",
    }
    with httpx.Client(timeout=60) as client:
        resp = client.get(ARCHIVE_URL, params=params)
        resp.raise_for_status()
        data = resp.json()["daily"]

    rows = []
    for i, date_str in enumerate(data["time"]):
        month = int(date_str[5:7])
        temp_max = data["temperature_2m_max"][i]
        temp_min = data["temperature_2m_min"][i]
        precip_sum = data["precipitation_sum"][i] or 0
        wind_max = data["wind_speed_10m_max"][i]
        uv_max = data["uv_index_max"][i] or 0
        humidity = data["relative_humidity_2m_mean"][i]
        if None in (temp_max, temp_min, wind_max, humidity):
            continue
        label, precip_prob = label_from_row(temp_max, temp_min, precip_sum, wind_max, uv_max)
        rows.append([month, lat, temp_max, temp_min, humidity, precip_prob, wind_max, uv_max, label])
    return rows


def main():
    all_rows = []
    for name, lat, lon in CITIES:
        try:
            all_rows.extend(fetch_city_history(name, lat, lon))
        except Exception as e:
            print(f"  skipped {name}: {e}")
        time.sleep(1)  # be polite to the free API

    df = pd.DataFrame(all_rows, columns=FEATURES + ["label"])
    print(f"Collected {len(df)} real daily observations across {len(CITIES)} cities.")

    X = df[FEATURES].values
    y = df["label"].values
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    clf = RandomForestClassifier(n_estimators=300, max_depth=12, random_state=42, class_weight="balanced")
    clf.fit(X_train, y_train)
    preds = clf.predict(X_test)
    print(classification_report(y_test, preds, target_names=LABELS))

    out_dir = Path(__file__).parent
    joblib.dump(clf, out_dir / "weather_risk_model.pkl")
    with open(out_dir / "model_meta.json", "w") as f:
        json.dump({
            "features": FEATURES,
            "labels": LABELS,
            "trained_on": "open-meteo-historical-archive",
            "cities": [c[0] for c in CITIES],
            "date_range": [START_DATE, END_DATE],
            "n_samples": len(df),
        }, f, indent=2)
    print(f"Saved real-data model to {out_dir / 'weather_risk_model.pkl'}")


if __name__ == "__main__":
    main()
