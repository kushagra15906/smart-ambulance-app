"""
ml_predictor.py — ML Traffic Prediction Module
================================================
Trains a Random Forest model on historical vehicle counts.
Saves/loads model as traffic_model.pkl.

Functions:
  train_model()          → train and save model
  predict_traffic()      → predict next N minutes from history
  load_or_train_model()  → smart load with auto-training fallback
"""

import logging
import math
import os
import pickle
import time
import threading
from collections import deque
from datetime import datetime
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

MODEL_PATH    = "traffic_model.pkl"
HISTORY_SIZE  = 100    # rolling window of vehicle count observations
MIN_TRAIN     = 20     # minimum observations needed before ML model is useful
RETRAIN_EVERY = 500    # retrain after this many new observations

# Time-of-day peak multipliers (hour → multiplier)
_TIME_PATTERN = {
    0: 0.2, 1: 0.2, 2: 0.2, 3: 0.2, 4: 0.3, 5: 0.4,
    6: 0.6, 7: 0.8, 8: 1.0, 9: 1.0, 10: 0.8, 11: 0.7,
    12: 0.8, 13: 0.7, 14: 0.6, 15: 0.7, 16: 0.9, 17: 1.0,
    18: 1.0, 19: 0.9, 20: 0.7, 21: 0.5, 22: 0.4, 23: 0.3,
}


# ── Feature Engineering ───────────────────────────────────────────────────────

def _extract_features(history: list, minutes_ahead: int = 1) -> np.ndarray:
    """
    Convert rolling history into ML feature vector.

    Features:
      - Last 5 vehicle counts (lagged values)
      - Rolling mean of last 10 counts
      - Rolling std  of last 10 counts
      - Linear trend slope (last 10)
      - Time-of-day multiplier
      - Minutes-ahead target
      - Hour of day (cyclic: sin + cos)
      - Day of week (cyclic: sin + cos)

    Returns 1D numpy array of shape (13,).
    """
    arr = np.array(history, dtype=float)

    # Pad if too short
    if len(arr) < 10:
        arr = np.pad(arr, (10 - len(arr), 0), constant_values=arr[0] if len(arr) else 0)

    # Last 5 values (lag features)
    lags = arr[-5:].tolist()

    # Rolling statistics over last 10
    window   = arr[-10:]
    roll_mean = float(np.mean(window))
    roll_std  = float(np.std(window)) if len(window) > 1 else 0.0

    # Linear trend (slope of last 10)
    if len(window) >= 2:
        x      = np.arange(len(window))
        slope  = float(np.polyfit(x, window, 1)[0])
    else:
        slope = 0.0

    # Time features
    now       = datetime.now()
    hour      = now.hour
    dow       = now.weekday()      # 0=Monday
    time_mult = _TIME_PATTERN.get(hour, 0.5)

    # Cyclic encoding to avoid discontinuity at midnight / week boundary
    hour_sin  = math.sin(2 * math.pi * hour / 24)
    hour_cos  = math.cos(2 * math.pi * hour / 24)
    dow_sin   = math.sin(2 * math.pi * dow / 7)
    dow_cos   = math.cos(2 * math.pi * dow / 7)

    features = lags + [
        roll_mean, roll_std, slope,
        time_mult, float(minutes_ahead),
        hour_sin, hour_cos, dow_sin, dow_cos,
    ]
    return np.array(features, dtype=float).reshape(1, -1)


def _generate_training_data(history: list) -> tuple[np.ndarray, np.ndarray]:
    """
    Create (X, y) training pairs from rolling history.
    Each sample: features from window[i-10:i] → target = window[i+1]
    """
    X_rows, y_rows = [], []
    arr = np.array(history, dtype=float)

    for i in range(10, len(arr) - 5):
        window = arr[max(0, i-10):i].tolist()
        for ahead in range(1, 6):       # predict 1–5 minutes ahead
            if i + ahead >= len(arr):
                continue
            target  = float(arr[i + ahead])
            feats   = _extract_features(window, ahead)[0]
            X_rows.append(feats)
            y_rows.append(target)

    if not X_rows:
        return np.array([]), np.array([])

    return np.array(X_rows), np.array(y_rows)


# ── Model Training ────────────────────────────────────────────────────────────

def train_model(history: list, save_path: str = MODEL_PATH) -> object:
    """
    Train a Random Forest regressor on historical vehicle counts.
    Saves model to pickle file and returns the trained model.

    Falls back to Linear Regression if sklearn RF fails.
    """
    try:
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.linear_model  import LinearRegression
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline      import Pipeline
        from sklearn.model_selection import cross_val_score
    except ImportError:
        log.error("[ML] scikit-learn not installed. Run: pip install scikit-learn")
        return None

    if len(history) < MIN_TRAIN:
        log.warning("[ML] Not enough data to train (%d < %d). Using fallback.",
                    len(history), MIN_TRAIN)
        return None

    log.info("[ML] Training on %d observations...", len(history))
    X, y = _generate_training_data(history)

    if len(X) == 0:
        log.warning("[ML] Could not generate training data")
        return None

    # Random Forest with a scaler pipeline
    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("model",  RandomForestRegressor(
            n_estimators  = 100,
            max_depth     = 8,
            min_samples_leaf = 2,
            random_state  = 42,
            n_jobs        = -1,
        )),
    ])

    try:
        pipeline.fit(X, y)

        # Quick CV score for logging
        if len(X) >= 10:
            scores = cross_val_score(pipeline, X, y, cv=min(3, len(X)//4),
                                     scoring="neg_mean_absolute_error")
            log.info("[ML] CV MAE: %.2f ± %.2f",
                     -scores.mean(), scores.std())

    except Exception as e:
        log.warning("[ML] RF failed (%s) — falling back to Linear Regression", e)
        pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("model",  LinearRegression()),
        ])
        pipeline.fit(X, y)

    # Save to disk
    try:
        with open(save_path, "wb") as f:
            pickle.dump(pipeline, f)
        log.info("[ML] Model saved to %s", save_path)
    except Exception as e:
        log.error("[ML] Failed to save model: %s", e)

    return pipeline


def load_model(path: str = MODEL_PATH) -> Optional[object]:
    """Load a previously saved model from disk."""
    if not os.path.exists(path):
        log.info("[ML] No saved model at %s", path)
        return None
    try:
        with open(path, "rb") as f:
            model = pickle.load(f)
        log.info("[ML] Model loaded from %s", path)
        return model
    except Exception as e:
        log.error("[ML] Failed to load model: %s", e)
        return None


# ── Prediction ────────────────────────────────────────────────────────────────

def predict_traffic(
    history    : list,
    model      : object,
    minutes_ahead: int = 2,
) -> dict:
    """
    Predict vehicle count N minutes ahead using the trained ML model.

    If model is None or history too short → falls back to
    Weighted Moving Average (WMA) estimate.

    Returns:
    {
      "predicted"     : float,   ← main prediction value
      "method"        : str,     ← "ml_model" | "wma_fallback"
      "confidence"    : float,
      "congestion"    : str,
      "minutes_ahead" : int,
    }
    """
    if len(history) < 3:
        return _fallback_prediction(history, minutes_ahead)

    # ── ML model prediction ───────────────────────────────────────────────────
    if model is not None:
        try:
            feats     = _extract_features(history, minutes_ahead)
            predicted = float(model.predict(feats)[0])
            predicted = max(0.0, min(100.0, predicted))     # clamp

            confidence = max(0.3, 1.0 - (minutes_ahead * 0.08))

            return {
                "predicted"    : round(predicted, 1),
                "method"       : "ml_model",
                "confidence"   : round(confidence, 2),
                "congestion"   : _congestion(predicted),
                "minutes_ahead": minutes_ahead,
            }
        except Exception as e:
            log.warning("[ML] Prediction failed: %s — using WMA fallback", e)

    # ── WMA fallback ──────────────────────────────────────────────────────────
    return _fallback_prediction(history, minutes_ahead)


def _fallback_prediction(history: list, minutes_ahead: int) -> dict:
    """
    Weighted Moving Average fallback when ML model is unavailable.
    """
    arr     = np.array(history[-10:], dtype=float)
    weights = np.linspace(0.5, 1.5, len(arr))
    weights /= weights.sum()
    wma     = float(np.dot(weights, arr))

    # Simple trend adjustment
    if len(arr) >= 4:
        trend = float(arr[-1] - arr[-4]) / 3
    else:
        trend = 0.0

    time_mult = _TIME_PATTERN.get(datetime.now().hour, 0.5)
    predicted = wma + (trend * minutes_ahead * 0.3)
    predicted = max(0.0, min(100.0, predicted * (0.7 + 0.3 * time_mult)))

    return {
        "predicted"    : round(predicted, 1),
        "method"       : "wma_fallback",
        "confidence"   : round(max(0.3, 0.8 - minutes_ahead * 0.1), 2),
        "congestion"   : _congestion(predicted),
        "minutes_ahead": minutes_ahead,
    }


def predict_horizon(history: list, model: object) -> list:
    """Predict traffic at 1, 2, 3, 4, 5 minutes ahead."""
    return [predict_traffic(history, model, m) for m in range(1, 6)]


def _congestion(c: float) -> str:
    if c < 20: return "LOW"
    if c < 50: return "MEDIUM"
    if c < 75: return "HIGH"
    return "CRITICAL"


# ── Traffic History Manager ───────────────────────────────────────────────────

class TrafficHistoryManager:
    """
    Thread-safe rolling history of vehicle counts per signal.
    Triggers model retraining when enough new data has accumulated.
    """

    def __init__(self, signal_ids: list):
        self._histories  = {s: deque(maxlen=HISTORY_SIZE) for s in signal_ids}
        self._model      = load_model()     # try loading from disk
        self._lock       = threading.Lock()
        self._obs_count  = 0               # observations since last retrain

        # If no model found, use empty history and WMA for now
        if self._model is None:
            log.info("[ML] No pretrained model found — using WMA until enough data")

    def add(self, signal_id: str, vehicle_count: int):
        """Record a new vehicle count for a signal."""
        with self._lock:
            if signal_id in self._histories:
                self._histories[signal_id].append(int(vehicle_count))
                self._obs_count += 1

        # Retrain when we have accumulated enough new data
        if self._obs_count >= RETRAIN_EVERY or (
                self._model is None and self._obs_count >= MIN_TRAIN):
            threading.Thread(target=self._retrain, daemon=True).start()

    def get_history(self, signal_id: str) -> list:
        """Return a copy of the history list for one signal."""
        with self._lock:
            return list(self._histories.get(signal_id, []))

    def get_all_history(self) -> list:
        """Flatten all signal histories into one list for global training."""
        with self._lock:
            combined = []
            for h in self._histories.values():
                combined.extend(list(h))
        return combined

    def predict(self, signal_id: str, minutes: int = 2) -> dict:
        """Predict traffic for one signal N minutes ahead."""
        history = self.get_history(signal_id)
        with self._lock:
            model = self._model
        return predict_traffic(history, model, minutes)

    def predict_horizon(self, signal_id: str) -> list:
        """Predict 1–5 minutes for one signal."""
        history = self.get_history(signal_id)
        with self._lock:
            model = self._model
        return predict_horizon(history, model)

    def _retrain(self):
        """Background retraining on accumulated data."""
        log.info("[ML] Retraining model...")
        all_data = self.get_all_history()
        new_model = train_model(all_data)
        if new_model:
            with self._lock:
                self._model = new_model
                self._obs_count = 0
            log.info("[ML] Model retrained and updated ✓")

    def force_train(self):
        """Force immediate retraining (called at startup with seed data)."""
        self._retrain()

    @property
    def model_ready(self) -> bool:
        with self._lock:
            return self._model is not None