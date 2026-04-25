"""
traffic_predictor.py — AI Traffic Prediction Module
=====================================================
Uses Weighted Moving Average + time-of-day patterns
to predict short-term traffic (1–5 minutes ahead).

Each signal node maintains a rolling history window.
Predictions are combined with real-time YOLO counts.
"""

import time
import math
import threading
from collections import deque
from datetime import datetime
from typing import Optional

# ── Configuration ─────────────────────────────────────────────────────────────

HISTORY_WINDOW   = 30     # keep last 30 readings per signal
PREDICTION_STEPS = 5      # predict 1 to 5 minutes ahead
WMA_WEIGHTS      = [      # most recent reading has highest weight
    0.35, 0.25, 0.15,
    0.10, 0.07, 0.04,
    0.02, 0.01, 0.005, 0.005
]

# Time-of-day congestion multipliers (hour → multiplier)
# Peaks: 8–10 AM and 5–8 PM
TIME_OF_DAY_PATTERN = {
    0: 0.2,  1: 0.2,  2: 0.2,  3: 0.2,
    4: 0.3,  5: 0.4,  6: 0.6,  7: 0.8,
    8: 1.0,  9: 1.0,  10: 0.8, 11: 0.7,
    12: 0.8, 13: 0.7, 14: 0.6, 15: 0.7,
    16: 0.9, 17: 1.0, 18: 1.0, 19: 0.9,
    20: 0.7, 21: 0.5, 22: 0.4, 23: 0.3,
}


def _time_multiplier() -> float:
    """Return congestion multiplier based on current hour."""
    hour = datetime.now().hour
    return TIME_OF_DAY_PATTERN.get(hour, 0.5)


# ── Traffic History Store ─────────────────────────────────────────────────────

class SignalTrafficHistory:
    """
    Maintains rolling history of vehicle counts for one signal.
    Thread-safe with a lock.
    """

    def __init__(self, signal_id: str, max_size: int = HISTORY_WINDOW):
        self.signal_id  = signal_id
        self._history   = deque(maxlen=max_size)  # list of (timestamp, vehicle_count)
        self._lock      = threading.Lock()

    def add(self, vehicle_count: int):
        """Record a new vehicle count observation."""
        with self._lock:
            self._history.append({
                "ts"   : time.time(),
                "count": int(vehicle_count),
            })

    def get_recent(self, n: int = 10) -> list:
        """Return the n most recent readings (newest last)."""
        with self._lock:
            history = list(self._history)
        return history[-n:]

    def average(self) -> float:
        """Simple mean of all stored values."""
        with self._lock:
            if not self._history:
                return 0.0
            return sum(r["count"] for r in self._history) / len(self._history)

    def weighted_moving_average(self) -> float:
        """
        Weighted Moving Average (WMA).
        Recent readings carry more weight.
        Returns predicted current traffic level.
        """
        with self._lock:
            history = list(self._history)

        if not history:
            return 0.0

        # Use up to len(WMA_WEIGHTS) most recent readings
        recent = [r["count"] for r in history[-len(WMA_WEIGHTS):]]
        recent.reverse()    # most recent first

        weights  = WMA_WEIGHTS[:len(recent)]
        total_w  = sum(weights)
        wma      = sum(v * w for v, w in zip(recent, weights)) / total_w
        return wma

    def trend(self) -> float:
        """
        Compute rate of change (slope) between first and last half of history.
        Positive = traffic increasing, Negative = decreasing.
        """
        with self._lock:
            history = list(self._history)

        if len(history) < 4:
            return 0.0

        mid   = len(history) // 2
        first = sum(r["count"] for r in history[:mid]) / mid
        last  = sum(r["count"] for r in history[mid:]) / (len(history) - mid)
        return last - first   # vehicles per window


# ── Predictor ─────────────────────────────────────────────────────────────────

class TrafficPredictor:
    """
    Central prediction engine for all signal nodes.

    Usage:
        predictor = TrafficPredictor()
        predictor.update("S1", 42)          # feed new observation
        pred = predictor.predict("S1", 3)   # predict 3 minutes ahead
    """

    def __init__(self):
        self._signals: dict[str, SignalTrafficHistory] = {}
        self._lock = threading.Lock()

    def _ensure_signal(self, signal_id: str):
        if signal_id not in self._signals:
            with self._lock:
                if signal_id not in self._signals:
                    self._signals[signal_id] = SignalTrafficHistory(signal_id)

    def update(self, signal_id: str, vehicle_count: int):
        """
        Feed a new vehicle count observation for a signal.
        Called whenever YOLO detects vehicles OR simulation updates.
        """
        self._ensure_signal(signal_id)
        self._signals[signal_id].add(vehicle_count)

    def predict(self, signal_id: str, minutes_ahead: int = 1) -> dict:
        """
        Predict vehicle count N minutes into the future.

        Formula:
          predicted = WMA + (trend × minutes) × time_multiplier

        Returns dict with predicted value + confidence + congestion label.
        """
        self._ensure_signal(signal_id)
        hist  = self._signals[signal_id]

        wma         = hist.weighted_moving_average()
        trend_rate  = hist.trend()
        time_mult   = _time_multiplier()

        # Projected value = WMA shifted by trend, scaled by time-of-day
        raw_pred    = wma + (trend_rate * minutes_ahead * 0.3)
        adjusted    = raw_pred * (0.7 + 0.3 * time_mult)   # blend with pattern
        predicted   = max(0.0, min(100.0, adjusted))         # clamp 0–100

        # Confidence decreases with prediction horizon
        confidence  = max(0.3, 1.0 - (minutes_ahead * 0.12))

        return {
            "signal_id"     : signal_id,
            "minutes_ahead" : minutes_ahead,
            "predicted"     : round(predicted, 1),
            "current_wma"   : round(wma, 1),
            "trend"         : round(trend_rate, 2),
            "confidence"    : round(confidence, 2),
            "congestion"    : _congestion_label(predicted),
            "time_multiplier": round(time_mult, 2),
        }

    def predict_all(self, signal_ids: list, minutes_ahead: int = 2) -> dict:
        """Predict traffic for multiple signals at once."""
        return {
            sig: self.predict(sig, minutes_ahead)
            for sig in signal_ids
        }

    def predict_horizon(self, signal_id: str) -> list:
        """
        Predict traffic at 1, 2, 3, 4, 5 minutes ahead.
        Returns a list of prediction dicts.
        """
        return [self.predict(signal_id, m) for m in range(1, PREDICTION_STEPS + 1)]

    def get_history(self, signal_id: str) -> list:
        """Return raw history for a signal (for dashboard/debug)."""
        self._ensure_signal(signal_id)
        return self._signals[signal_id].get_recent(20)

    def summary(self, signal_id: str) -> dict:
        """Full summary: current WMA + trend + 1/3/5 min predictions."""
        self._ensure_signal(signal_id)
        return {
            "signal_id"       : signal_id,
            "current_wma"     : round(self._signals[signal_id].weighted_moving_average(), 1),
            "trend"           : round(self._signals[signal_id].trend(), 2),
            "prediction_1min" : self.predict(signal_id, 1)["predicted"],
            "prediction_3min" : self.predict(signal_id, 3)["predicted"],
            "prediction_5min" : self.predict(signal_id, 5)["predicted"],
            "history_count"   : len(self._signals[signal_id].get_recent(HISTORY_WINDOW)),
        }


def _congestion_label(count: float) -> str:
    if count < 20: return "LOW"
    if count < 50: return "MEDIUM"
    if count < 75: return "HIGH"
    return "CRITICAL"


# ── Singleton instance (shared across Flask app) ──────────────────────────────
predictor = TrafficPredictor()