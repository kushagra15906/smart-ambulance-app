"""
camera_pipeline.py — Real-Time Camera Detection Pipeline
===========================================================
Captures frames from webcam/RTSP stream using OpenCV.
Runs dual YOLO detection + feeds results to ML history.
Designed to run as a background thread.

Usage:
  pipeline = CameraPipeline(signal_id="S1", source=0)
  pipeline.start()
  result = pipeline.latest_result()
  pipeline.stop()
"""

import cv2
import logging
import threading
import time
from typing import Optional

import numpy as np

from yolo_detector import detector
from ml_predictor  import TrafficHistoryManager

log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

FRAME_INTERVAL_S   = 2.0    # process one frame every N seconds
CONFIRM_FRAMES     = 3      # require N consecutive ambulance detections
DISPLAY_ENABLED    = False  # set True to show OpenCV window (dev only)


class CameraPipeline:
    """
    Runs dual YOLO detection on a video source in a background thread.
    Stores the latest detection result for the Flask API to read.

    One instance per camera/signal junction.
    """

    def __init__(self, signal_id: str, source=0,
                 history_manager: Optional[TrafficHistoryManager] = None):
        self.signal_id       = signal_id
        self.source          = source
        self.history_manager = history_manager

        self._thread         = None
        self._running        = False
        self._result         = _empty_result(signal_id)
        self._lock           = threading.Lock()
        self._amb_streak     = 0      # consecutive frames with ambulance

    def start(self):
        """Start the detection thread."""
        if not detector.is_ready():
            log.info("[CAM] Loading YOLO models...")
            if not detector.load_models():
                log.error("[CAM] Failed to load models — pipeline will not start")
                return
        self._running = True
        self._thread  = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        log.info("[CAM] Pipeline started | signal=%s source=%s",
                 self.signal_id, self.source)

    def stop(self):
        """Stop the detection thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        log.info("[CAM] Pipeline stopped | signal=%s", self.signal_id)

    def latest_result(self) -> dict:
        """Return the most recent detection result (thread-safe)."""
        with self._lock:
            return dict(self._result)

    # ── Background Thread ─────────────────────────────────────────────────────

    def _run(self):
        """Main detection loop — runs in background thread."""
        cap = self._open_source()
        if cap is None:
            log.error("[CAM] Cannot open source: %s", self.source)
            return

        last_frame_time = 0.0
        frame_count     = 0

        while self._running:
            ret, frame = cap.read()
            if not ret:
                log.warning("[CAM] Frame read failed — retrying in 1s")
                time.sleep(1)
                cap.release()
                cap = self._open_source()
                if cap is None:
                    break
                continue

            now = time.time()
            # Rate-limit: only process every FRAME_INTERVAL_S seconds
            if now - last_frame_time < FRAME_INTERVAL_S:
                time.sleep(0.05)
                continue

            last_frame_time = now
            frame_count += 1

            # ── Run dual YOLO detection ───────────────────────────────────────
            detection = detector.detect_all(frame)

            # Ambulance confirmation (require N consecutive frames)
            if detection["ambulance_detected"]:
                self._amb_streak += 1
            else:
                self._amb_streak = max(0, self._amb_streak - 1)

            confirmed_ambulance = self._amb_streak >= CONFIRM_FRAMES

            # ── Build result ──────────────────────────────────────────────────
            result = {
                "signal_id"         : self.signal_id,
                "vehicle_count"     : detection["vehicle_count"],
                "vehicles_by_class" : detection["vehicles_by_class"],
                "ambulance_detected": confirmed_ambulance,
                "ambulance_conf"    : detection["ambulance_conf"],
                "ambulance_bbox"    : detection["ambulance_bbox"],
                "frame_count"       : frame_count,
                "timestamp"         : now,
            }

            with self._lock:
                self._result = result

            # ── Feed into ML history ──────────────────────────────────────────
            if self.history_manager:
                self.history_manager.add(
                    self.signal_id,
                    detection["vehicle_count"]
                )

            # ── Optional display window ───────────────────────────────────────
            if DISPLAY_ENABLED and detection["annotated_frame"] is not None:
                _draw_hud(detection["annotated_frame"],
                          detection["vehicle_count"],
                          confirmed_ambulance, self.signal_id)
                cv2.imshow(f"Camera — {self.signal_id}",
                           detection["annotated_frame"])
                if cv2.waitKey(1) & 0xFF in [ord("q"), 27]:
                    break

        cap.release()
        if DISPLAY_ENABLED:
            cv2.destroyAllWindows()

    def _open_source(self):
        """Open video capture source with retry."""
        try:
            src = int(self.source)
        except (ValueError, TypeError):
            src = self.source

        cap = cv2.VideoCapture(src)
        if not cap.isOpened():
            log.warning("[CAM] Cannot open %s", src)
            return None
        # Reduce buffer size to get fresh frames
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap


# ── Multi-Camera Manager ──────────────────────────────────────────────────────

class MultiCameraManager:
    """
    Manages multiple CameraPipelines — one per signal junction.
    Provides a unified interface for the Flask app.
    """

    def __init__(self, signal_configs: list[dict],
                 history_manager: TrafficHistoryManager):
        """
        signal_configs: list of {"signal_id": "S1", "source": 0}
        """
        self._pipelines = {}
        self._history   = history_manager

        for cfg in signal_configs:
            sig    = cfg["signal_id"]
            source = cfg.get("source", 0)
            self._pipelines[sig] = CameraPipeline(
                signal_id=sig, source=source, history_manager=history_manager)

    def start_all(self):
        """Start all camera pipelines."""
        for sig, pipe in self._pipelines.items():
            pipe.start()
        log.info("[CAM] %d pipelines started", len(self._pipelines))

    def stop_all(self):
        """Stop all camera pipelines."""
        for pipe in self._pipelines.values():
            pipe.stop()

    def get_result(self, signal_id: str) -> dict:
        """Get latest detection result for one signal."""
        pipe = self._pipelines.get(signal_id)
        return pipe.latest_result() if pipe else _empty_result(signal_id)

    def get_all_results(self) -> dict:
        """Get latest results for all signals."""
        return {sig: pipe.latest_result()
                for sig, pipe in self._pipelines.items()}

    def is_ambulance_detected(self) -> tuple[bool, str]:
        """
        Check if ambulance is detected at ANY camera.
        Returns (detected, signal_id_where_detected).
        """
        for sig, pipe in self._pipelines.items():
            r = pipe.latest_result()
            if r.get("ambulance_detected"):
                return True, sig
        return False, ""


# ── HUD Drawing ───────────────────────────────────────────────────────────────

def _draw_hud(frame, vehicle_count: int, amb_detected: bool, sig_id: str):
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 52), (7, 11, 20), -1)
    cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)
    cv2.putText(frame,
                f"Signal: {sig_id} | Vehicles: {vehicle_count}",
                (10, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1)
    if amb_detected:
        flash = int(time.time() * 3) % 2 == 0
        cv2.putText(frame, "AMBULANCE DETECTED",
                    (w - 260, 32), cv2.FONT_HERSHEY_SIMPLEX,
                    0.65, (0, 60, 255) if flash else (255, 255, 255), 2)


def _empty_result(signal_id: str) -> dict:
    return {
        "signal_id"         : signal_id,
        "vehicle_count"     : 0,
        "vehicles_by_class" : {},
        "ambulance_detected": False,
        "ambulance_conf"    : 0.0,
        "ambulance_bbox"    : [],
        "frame_count"       : 0,
        "timestamp"         : time.time(),
    }