"""
Trains the baseline "WeatherGPT Risk Index" model.

This is a REAL scikit-learn model, trained on a REAL dataset — but the
dataset here is synthetically generated from domain-informed rules (India's
climate: monsoon months, latitude bands, temperature/wind/UV extremes),
with random noise added so the model has to learn a genuine decision
boundary rather than memorize a lookup table.

Run this once to produce `weather_risk_model.pkl` so the app works out of
the box:

    python train_synthetic_baseline.py

For a stronger, production-grade model trained on REAL historical weather
observations (not synthetic), run `train_on_live_history.py` instead once
you have internet access — it pulls years of real daily data per city from
Open-Meteo's historical archive and trains on that.

Both scripts save to the same file / feature format, so the backend doesn't
care which one produced the model.
"""
import json
import numpy as np
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import joblib

RNG = np.random.default_rng(42)
N_SAMPLES = 30000

FEATURES = ["month", "latitude", "temp_max", "temp_min", "humidity", "precip_prob", "wind_max", "uv_max"]
LABELS = ["low", "moderate", "high", "severe"]


def is_monsoon(month, lat):
    # Broad approximation: monsoon (Jun-Sep) is wetter in the west coast /
    # lower latitudes, tapers off further north/inland.
    return 6 <= month <= 9


def generate_sample():
    month = RNG.integers(1, 13)
    latitude = RNG.uniform(8, 35)          # India's rough latitude span
    monsoon = is_monsoon(month, latitude)

    # Temperature: hotter pre-monsoon (Apr-Jun) & in lower latitudes, colder
    # in northern winter (Dec-Feb).
    base_temp = 30 - (latitude - 8) * 0.35
    if month in (4, 5, 6):
        base_temp += 6
    if month in (12, 1, 2):
        base_temp -= 8 + (latitude - 8) * 0.3
    temp_max = base_temp + RNG.normal(0, 4)
    temp_min = temp_max - RNG.uniform(6, 14)

    humidity = RNG.uniform(75, 95) if monsoon else RNG.uniform(20, 70)
    precip_prob = RNG.uniform(40, 95) if monsoon else RNG.uniform(0, 40)
    wind_max = RNG.uniform(5, 25) + (15 if monsoon and RNG.random() < 0.1 else 0)
    uv_max = RNG.uniform(3, 12) if month in range(3, 10) else RNG.uniform(1, 7)

    # Domain-informed risk label with noise so it's not a trivial threshold.
    score = 0
    score += 2 if precip_prob >= 75 else (1 if precip_prob >= 55 else 0)
    score += 2 if temp_max >= 42 else (1 if temp_max >= 38 else 0)
    score += 1 if temp_min <= 4 else 0
    score += 2 if wind_max >= 45 else (1 if wind_max >= 30 else 0)
    score += 1 if uv_max >= 9 else 0
    score += RNG.normal(0, 0.6)  # noise

    if score < 1.2:
        label = 0
    elif score < 2.6:
        label = 1
    elif score < 4.2:
        label = 2
    else:
        label = 3

    return [month, latitude, temp_max, temp_min, humidity, precip_prob, wind_max, uv_max], label


def main():
    X, y = [], []
    for _ in range(N_SAMPLES):
        feats, label = generate_sample()
        X.append(feats)
        y.append(label)
    X = np.array(X)
    y = np.array(y)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    clf = RandomForestClassifier(n_estimators=200, max_depth=10, random_state=42, class_weight="balanced")
    clf.fit(X_train, y_train)

    preds = clf.predict(X_test)
    print(classification_report(y_test, preds, target_names=LABELS))

    out_dir = Path(__file__).parent
    joblib.dump(clf, out_dir / "weather_risk_model.pkl")
    with open(out_dir / "model_meta.json", "w") as f:
        json.dump({
            "features": FEATURES,
            "labels": LABELS,
            "trained_on": "synthetic-domain-rules-v1",
            "n_samples": N_SAMPLES,
        }, f, indent=2)
    print(f"Saved model to {out_dir / 'weather_risk_model.pkl'}")


if __name__ == "__main__":
    main()
