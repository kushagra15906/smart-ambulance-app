"""
train_ml_model.py — Train and Save Traffic Prediction Model
=============================================================
Run this ONCE before starting the Flask server to pre-train
and save traffic_model.pkl.

Usage:
  python train_ml_model.py
  python train_ml_model.py --samples 500 --output traffic_model.pkl

The script generates realistic synthetic training data if no
real traffic history is available yet.
"""

import argparse
import logging
import math
import random
import pickle
import os
import numpy as np
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ── Time-of-day traffic profile ───────────────────────────────────────────────

TIME_PATTERN = {
    0: 0.2, 1: 0.2, 2: 0.2, 3: 0.2, 4: 0.3, 5: 0.4,
    6: 0.6, 7: 0.8, 8: 1.0, 9: 1.0, 10: 0.8, 11: 0.7,
    12: 0.8, 13: 0.7, 14: 0.6, 15: 0.7, 16: 0.9, 17: 1.0,
    18: 1.0, 19: 0.9, 20: 0.7, 21: 0.5, 22: 0.4, 23: 0.3,
}

# Different signals have different baseline densities
SIGNAL_BASELINES = {
    "S1": 15, "S2": 30, "S3": 10,
    "S4": 45, "S5": 22, "S6": 60,
    "S7": 8,  "S8": 18, "S9": 35,
}


def _generate_synthetic_history(n_samples: int = 200,
                                  signal_id: str = "S1") -> list:
    """
    Generate realistic synthetic vehicle count history.

    Models:
      - Daily traffic cycle (morning/evening peaks)
      - Random noise
      - Occasional traffic spikes (accidents/events)
      - Gradual trends
    """
    base      = SIGNAL_BASELINES.get(signal_id, 20)
    history   = []
    now       = datetime.now()

    for i in range(n_samples):
        # Go back in time
        ts   = now - timedelta(minutes=2 * (n_samples - i))
        hour = ts.hour

        # Base count from time-of-day
        count = base * TIME_PATTERN.get(hour, 0.5)

        # Gaussian noise
        count += random.gauss(0, 5)

        # Occasional spike
        if random.random() < 0.05:
            count += random.uniform(10, 30)

        # Gradual trend (slight increase over time)
        count += i * 0.02

        count = max(0, min(100, round(count)))
        history.append(count)

    return history


def _extract_features(history: list, minutes_ahead: int = 1) -> np.ndarray:
    """Same feature extraction as ml_predictor.py (must stay in sync)."""
    arr = np.array(history, dtype=float)
    if len(arr) < 10:
        arr = np.pad(arr, (10 - len(arr), 0), constant_values=arr[0] if len(arr) else 0)

    lags = arr[-5:].tolist()
    window    = arr[-10:]
    roll_mean = float(np.mean(window))
    roll_std  = float(np.std(window)) if len(window) > 1 else 0.0

    if len(window) >= 2:
        x     = np.arange(len(window))
        slope = float(np.polyfit(x, window, 1)[0])
    else:
        slope = 0.0

    now       = datetime.now()
    hour      = now.hour
    dow       = now.weekday()
    time_mult = TIME_PATTERN.get(hour, 0.5)

    hour_sin = math.sin(2 * math.pi * hour / 24)
    hour_cos = math.cos(2 * math.pi * hour / 24)
    dow_sin  = math.sin(2 * math.pi * dow / 7)
    dow_cos  = math.cos(2 * math.pi * dow / 7)

    features = lags + [roll_mean, roll_std, slope,
                       time_mult, float(minutes_ahead),
                       hour_sin, hour_cos, dow_sin, dow_cos]
    return np.array(features, dtype=float)


def generate_training_dataset(n_samples_per_signal: int = 300) -> tuple:
    """Generate X, y training arrays across all 9 signals."""
    X_all, y_all = [], []

    for sig_id, base in SIGNAL_BASELINES.items():
        log.info("  Generating data for %s (base=%d)", sig_id, base)
        history = _generate_synthetic_history(n_samples_per_signal, sig_id)

        arr = np.array(history, dtype=float)
        for i in range(10, len(arr) - 5):
            window = arr[max(0, i-10):i].tolist()
            for ahead in range(1, 6):
                if i + ahead >= len(arr): continue
                target = float(arr[i + ahead])
                feats  = _extract_features(window, ahead)
                X_all.append(feats)
                y_all.append(target)

    return np.array(X_all), np.array(y_all)


def train_and_save(n_samples: int = 300, output_path: str = "traffic_model.pkl"):
    """Train Random Forest model and save to disk."""
    try:
        from sklearn.ensemble        import RandomForestRegressor
        from sklearn.linear_model    import LinearRegression
        from sklearn.preprocessing   import StandardScaler
        from sklearn.pipeline        import Pipeline
        from sklearn.model_selection import cross_val_score
        from sklearn.metrics         import mean_absolute_error, r2_score
    except ImportError:
        log.error("scikit-learn not installed. Run: pip install scikit-learn")
        return

    log.info("=" * 55)
    log.info("  Traffic Prediction Model Training")
    log.info("  Samples per signal: %d | 9 signals", n_samples)
    log.info("=" * 55)

    log.info("\nGenerating training data...")
    X, y = generate_training_dataset(n_samples)
    log.info("Training set: %d samples, %d features", len(X), X.shape[1])

    # ── Random Forest Pipeline ────────────────────────────────────────────────
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("model",  RandomForestRegressor(
            n_estimators     = 150,
            max_depth        = 10,
            min_samples_leaf = 2,
            max_features     = "sqrt",
            random_state     = 42,
            n_jobs           = -1,
        )),
    ])

    log.info("\nTraining Random Forest (n_estimators=150)...")
    pipeline.fit(X, y)

    # ── Evaluation ────────────────────────────────────────────────────────────
    scores = cross_val_score(pipeline, X, y, cv=5,
                              scoring="neg_mean_absolute_error")
    log.info("\n📊 Cross-Validation Results:")
    log.info("  MAE:  %.2f ± %.2f vehicles", -scores.mean(), scores.std())

    y_pred = pipeline.predict(X)
    log.info("  R²:   %.4f", r2_score(y, y_pred))
    log.info("  MAE (train): %.2f", mean_absolute_error(y, y_pred))

    # ── Save ──────────────────────────────────────────────────────────────────
    with open(output_path, "wb") as f:
        pickle.dump(pipeline, f)

    size_kb = os.path.getsize(output_path) / 1024
    log.info("\n✓ Model saved to %s (%.1f KB)", output_path, size_kb)

    # ── Quick inference test ──────────────────────────────────────────────────
    test_history = [15, 18, 22, 25, 20, 18, 15, 20, 25, 30]
    test_feat    = _extract_features(test_history, 2).reshape(1, -1)
    test_pred    = pipeline.predict(test_feat)[0]
    log.info("\n🔬 Inference test:")
    log.info("  Input:  %s", test_history)
    log.info("  Predicted (2 min ahead): %.1f vehicles", test_pred)

    log.info("\n✓ Training complete. Start Flask server now.")
    return pipeline


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train traffic prediction ML model")
    parser.add_argument("--samples", type=int, default=300,
                        help="Number of synthetic samples per signal (default: 300)")
    parser.add_argument("--output",  default="traffic_model.pkl",
                        help="Output path for saved model (default: traffic_model.pkl)")
    args = parser.parse_args()

    train_and_save(n_samples=args.samples, output_path=args.output)