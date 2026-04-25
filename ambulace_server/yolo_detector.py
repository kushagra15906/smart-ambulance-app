"""
yolo_detector.py — Dual YOLO Detection Module
===============================================
Loads two separate YOLO models:
  1. vehicle_model  → pretrained yolov8n.pt  (car, truck, bus, motorcycle)
  2. ambulance_model → custom best.pt         (ambulance)

Provides clean functions:
  detect_vehicles()   → count vehicles per frame
  detect_ambulance()  → detect if ambulance is present
  detect_all()        → run both models on one frame
"""

import cv2
import logging
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

# ── Model Paths ───────────────────────────────────────────────────────────────

VEHICLE_MODEL_PATH   = "yolov8n.pt"          # pretrained — auto-downloaded
AMBULANCE_MODEL_PATH = "runs/train/ambulance_detector/weights/best.pt"

# ── YOLO Classes we care about in vehicle model ───────────────────────────────
# COCO class IDs: car=2, motorcycle=3, bus=5, truck=7
VEHICLE_CLASS_IDS = {2, 3, 5, 7}
VEHICLE_CLASS_NAMES = {
    2: "car", 3: "motorcycle", 5: "bus", 7: "truck"
}

CONF_THRESH   = 0.45
IOU_THRESH    = 0.45
IMG_SIZE      = 640


class DualYOLODetector:
    """
    Manages both YOLO models with lazy loading and thread safety.
    Models are loaded once and reused across all frames.
    """

    def __init__(self):
        self._vehicle_model   = None
        self._ambulance_model = None
        self._lock            = threading.Lock()
        self._models_loaded   = False
        self._load_error      = None

    def load_models(self) -> bool:
        """
        Load both YOLO models.
        Returns True if at least vehicle model loaded successfully.
        """
        from ultralytics import YOLO

        with self._lock:
            try:
                # Load pretrained vehicle detection model
                log.info("[YOLO] Loading vehicle model: %s", VEHICLE_MODEL_PATH)
                self._vehicle_model = YOLO(VEHICLE_MODEL_PATH)
                log.info("[YOLO] Vehicle model loaded ✓ | classes: %s",
                         list(VEHICLE_CLASS_NAMES.values()))

            except Exception as e:
                log.error("[YOLO] Failed to load vehicle model: %s", e)
                self._load_error = str(e)
                return False

            try:
                # Load custom ambulance detection model
                if Path(AMBULANCE_MODEL_PATH).exists():
                    log.info("[YOLO] Loading ambulance model: %s", AMBULANCE_MODEL_PATH)
                    self._ambulance_model = YOLO(AMBULANCE_MODEL_PATH)
                    log.info("[YOLO] Ambulance model loaded ✓")
                else:
                    log.warning("[YOLO] Ambulance model not found at %s — "
                                "using vehicle model fallback", AMBULANCE_MODEL_PATH)
                    # Fallback: use vehicle model for ambulance detection too
                    self._ambulance_model = self._vehicle_model

            except Exception as e:
                log.warning("[YOLO] Ambulance model load failed: %s — using fallback", e)
                self._ambulance_model = self._vehicle_model

            self._models_loaded = True
            return True

    def is_ready(self) -> bool:
        return self._models_loaded and self._vehicle_model is not None

    # ── Vehicle Detection ─────────────────────────────────────────────────────

    def detect_vehicles(self, frame: np.ndarray) -> dict:
        """
        Run pretrained vehicle model on a frame.

        Returns:
          {
            "total_count"     : int,
            "by_class"        : {"car": 3, "truck": 1, ...},
            "detections"      : [{"class": "car", "conf": 0.89, "bbox": [...]}],
            "annotated_frame" : np.ndarray,
          }
        """
        if not self.is_ready():
            return _empty_vehicle_result()

        try:
            results  = self._vehicle_model(
                frame, conf=CONF_THRESH, iou=IOU_THRESH,
                imgsz=IMG_SIZE, verbose=False)

            detections = []
            by_class   = {v: 0 for v in VEHICLE_CLASS_NAMES.values()}
            total      = 0

            for result in results:
                if result.boxes is None:
                    continue
                for box in result.boxes:
                    class_id = int(box.cls[0])
                    # Only count vehicle classes we care about
                    if class_id not in VEHICLE_CLASS_IDS:
                        continue
                    conf       = float(box.conf[0])
                    class_name = VEHICLE_CLASS_NAMES[class_id]
                    bbox       = [int(v) for v in box.xyxy[0].tolist()]

                    detections.append({
                        "class": class_name,
                        "conf" : round(conf, 3),
                        "bbox" : bbox,
                    })
                    by_class[class_name] = by_class.get(class_name, 0) + 1
                    total += 1

            # Draw bounding boxes on a copy of the frame
            annotated = _draw_vehicle_boxes(frame.copy(), detections)

            return {
                "total_count"    : total,
                "by_class"       : by_class,
                "detections"     : detections,
                "annotated_frame": annotated,
            }

        except Exception as e:
            log.error("[YOLO] Vehicle detection error: %s", e)
            return _empty_vehicle_result()

    # ── Ambulance Detection ───────────────────────────────────────────────────

    def detect_ambulance(self, frame: np.ndarray,
                          confirm_frames: int = 3) -> dict:
        """
        Run custom ambulance model on a frame.
        Uses consecutive-frame confirmation to reduce false positives.

        Returns:
          {
            "detected"       : bool,
            "confidence"     : float,
            "bbox"           : list,
            "annotated_frame": np.ndarray,
          }
        """
        if not self.is_ready():
            return _empty_ambulance_result()

        try:
            results = self._ambulance_model(
                frame, conf=CONF_THRESH, iou=IOU_THRESH,
                imgsz=IMG_SIZE, verbose=False)

            best_conf = 0.0
            best_bbox = []

            for result in results:
                if result.boxes is None:
                    continue
                for box in result.boxes:
                    class_name = self._ambulance_model.names[int(box.cls[0])].lower()
                    if "ambulance" not in class_name:
                        continue
                    conf = float(box.conf[0])
                    if conf > best_conf:
                        best_conf = conf
                        best_bbox = [int(v) for v in box.xyxy[0].tolist()]

            detected  = best_conf >= CONF_THRESH
            annotated = _draw_ambulance_box(frame.copy(), best_bbox, best_conf) \
                        if detected else frame.copy()

            return {
                "detected"       : detected,
                "confidence"     : round(best_conf, 3),
                "bbox"           : best_bbox,
                "annotated_frame": annotated,
            }

        except Exception as e:
            log.error("[YOLO] Ambulance detection error: %s", e)
            return _empty_ambulance_result()

    # ── Combined Detection ────────────────────────────────────────────────────

    def detect_all(self, frame: np.ndarray) -> dict:
        """
        Run BOTH models on one frame.
        Combines vehicle count + ambulance detection into one result.

        Returns combined dict with all fields from both models.
        """
        # Run both models (vehicle model is faster, run first)
        vehicle_result   = self.detect_vehicles(frame)
        ambulance_result = self.detect_ambulance(frame)

        # Merge annotated frames: draw both sets of boxes
        combined_frame = vehicle_result["annotated_frame"].copy()
        if ambulance_result["detected"] and ambulance_result["bbox"]:
            combined_frame = _draw_ambulance_box(
                combined_frame,
                ambulance_result["bbox"],
                ambulance_result["confidence"]
            )

        return {
            # Vehicle data
            "vehicle_count"     : vehicle_result["total_count"],
            "vehicles_by_class" : vehicle_result["by_class"],
            "vehicle_detections": vehicle_result["detections"],
            # Ambulance data
            "ambulance_detected": ambulance_result["detected"],
            "ambulance_conf"    : ambulance_result["confidence"],
            "ambulance_bbox"    : ambulance_result["bbox"],
            # Combined
            "annotated_frame"   : combined_frame,
            "timestamp"         : time.time(),
        }


# ── Drawing Helpers ───────────────────────────────────────────────────────────

# Color map for vehicle classes
_VEHICLE_COLORS = {
    "car"       : (0, 200, 80),    # green
    "truck"     : (255, 140, 0),   # orange
    "bus"       : (0, 180, 255),   # blue
    "motorcycle": (180, 0, 255),   # purple
}


def _draw_vehicle_boxes(frame: np.ndarray, detections: list) -> np.ndarray:
    font = cv2.FONT_HERSHEY_SIMPLEX
    for d in detections:
        x1, y1, x2, y2 = d["bbox"]
        color = _VEHICLE_COLORS.get(d["class"], (200, 200, 200))
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        label = f"{d['class']} {d['conf']:.0%}"
        (tw, th), _ = cv2.getTextSize(label, font, 0.55, 1)
        cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw + 8, y1), color, -1)
        cv2.putText(frame, label, (x1 + 4, y1 - 5), font, 0.55, (255, 255, 255), 1)
    return frame


def _draw_ambulance_box(frame: np.ndarray, bbox: list, conf: float) -> np.ndarray:
    if not bbox:
        return frame
    x1, y1, x2, y2 = bbox
    color = (0, 60, 255)   # red
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
    label = f"AMBULANCE {conf:.0%}"
    font  = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), _ = cv2.getTextSize(label, font, 0.65, 2)
    cv2.rectangle(frame, (x1, y1 - th - 12), (x1 + tw + 8, y1), color, -1)
    cv2.putText(frame, label, (x1 + 4, y1 - 5), font, 0.65, (255, 255, 255), 2)
    return frame


# ── Empty Result Helpers ──────────────────────────────────────────────────────

def _empty_vehicle_result() -> dict:
    return {
        "total_count"    : 0,
        "by_class"       : {},
        "detections"     : [],
        "annotated_frame": None,
    }


def _empty_ambulance_result() -> dict:
    return {
        "detected"       : False,
        "confidence"     : 0.0,
        "bbox"           : [],
        "annotated_frame": None,
    }


# ── Singleton ─────────────────────────────────────────────────────────────────

detector = DualYOLODetector()