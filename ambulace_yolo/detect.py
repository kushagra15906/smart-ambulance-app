"""
detect.py — YOLOv8 Ambulance Detector v3
==========================================
Hybrid system: YOLO camera detection → POST to Flask /detection
Per-signal detection with confidence thresholding
Fail-safe: continues if Flask is unreachable
"""

import argparse
import time
import threading
import math
import cv2
import numpy as np
import requests
from ultralytics import YOLO
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

MODEL_PATH    = r"C:\Users\Lenovo\ece app kush\ambulace_yolo\runs\detect\train3\weights\best.pt"
FLASK_URL     = "http://127.0.0.1:5000"
CONF_THRESH   = 0.45
IOU_THRESH    = 0.45
IMG_SIZE      = 640

# Camera-to-signal mapping
# Each camera is mounted at a specific signal node
# Change CAMERA_SIGNAL_ID to match your physical setup
CAMERA_SIGNAL_ID = "S1"    # Which signal this camera covers

# Detection cooldown — don't spam Flask
DETECTION_COOLDOWN_S = 2.0

# ── Colors ────────────────────────────────────────────────────────────────────

CLASS_COLORS = {
    "ambulance": (0,   60,  255),
    "Ambulance": (0,   60,  255),
    "car"      : (0,   200, 80),
    "Car"      : (0,   200, 80),
    "truck"    : (255, 140, 0),
    "Truck"    : (255, 140, 0),
}

CLASS_ICONS = {
    "ambulance": "🚑", "Ambulance": "🚑",
    "car"      : "🚗", "Car"      : "🚗",
    "truck"    : "🚛", "Truck"    : "🚛",
}


def get_color(class_name: str) -> tuple:
    if class_name in CLASS_COLORS:
        return CLASS_COLORS[class_name]
    for k, v in CLASS_COLORS.items():
        if k.lower() == class_name.lower():
            return v
    return (200, 200, 200)

# ── Flask Communication ───────────────────────────────────────────────────────

_last_sent   = 0.0
_flask_ok    = True     # Track if Flask is reachable

def notify_flask_detection(sig_id: str, detected: bool,
                            confidence: float, bbox: list):
    """
    POST ambulance detection result to /detection endpoint.
    Runs in background thread — never blocks camera loop.
    Implements fail-safe: logs warning if Flask unreachable.
    """
    global _last_sent, _flask_ok

    now = time.time()
    if now - _last_sent < DETECTION_COOLDOWN_S:
        return
    _last_sent = now

    payload = {
        "signal_id"   : sig_id,
        "detected"    : detected,
        "confidence"  : round(confidence, 3),
        "bbox"        : bbox,
        "ambulance_id": "CAM001",
        "source"      : "yolo_camera",
        "timestamp"   : time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    try:
        resp = requests.post(
            f"{FLASK_URL}/detection",
            json=payload,
            timeout=2,
        )
        if resp.status_code == 200:
            data         = resp.json()
            action       = data.get("action_taken", "NONE")
            sig_state    = data.get("signal_state", "?")
            _flask_ok    = True
            if detected:
                print(f"\n  ✓ Flask → Signal {sig_id}: {action} | state={sig_state}")
        else:
            print(f"\n  ✗ Flask error: {resp.status_code}")
    except requests.exceptions.ConnectionError:
        if _flask_ok:   # Only warn once
            print(f"\n  ⚠ Flask unreachable — running in standalone mode")
        _flask_ok = False
    except Exception as e:
        print(f"\n  ✗ Detection send error: {e}")


# ── Drawing Helpers ───────────────────────────────────────────────────────────

def draw_detection(frame, box, label, conf, color):
    x1, y1, x2, y2 = map(int, box)
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    text = f"{label} {conf:.0%}"
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), _ = cv2.getTextSize(text, font, 0.6, 2)
    cv2.rectangle(frame, (x1, y1 - th - 12), (x1 + tw + 12, y1), color, -1)
    cv2.putText(frame, text, (x1 + 6, y1 - 6), font, 0.6, (255, 255, 255), 2)
    return frame


def draw_hud(frame, fps: float, detections: list,
             is_amb: bool, flask_ok: bool, sig_id: str):
    h, w = frame.shape[:2]

    # Top bar
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 56), (7, 11, 20), -1)
    cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)
    cv2.putText(frame, f"SMART AMBULANCE DETECTOR | Signal: {sig_id}",
                (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
    cv2.putText(frame, f"FPS: {fps:.1f}",
                (w - 110, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 100), 1)

    # Flask status indicator
    flask_color = (0, 220, 100) if flask_ok else (0, 100, 255)
    flask_label = "FLASK OK" if flask_ok else "FLASK OFFLINE"
    cv2.putText(frame, flask_label,
                (w - 130, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.4, flask_color, 1)

    # Bottom bar
    overlay2 = frame.copy()
    cv2.rectangle(overlay2, (0, h - 56), (w, h), (7, 11, 20), -1)
    cv2.addWeighted(overlay2, 0.8, frame, 0.2, 0, frame)
    cv2.putText(frame, f"Objects: {len(detections)}",
                (10, h - 28), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)

    # Ambulance alert
    if is_amb:
        alert = "AMBULANCE DETECTED — SIGNAL CONTROL ACTIVE"
        (aw, _), _ = cv2.getTextSize(alert, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        ax  = (w - aw) // 2
        flash = int(time.time() * 3) % 2 == 0
        if flash:
            cv2.rectangle(frame, (ax - 10, h - 52), (ax + aw + 10, h - 8),
                          (0, 0, 180), -1)
        cv2.putText(frame, alert, (ax, h - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (255, 255, 255) if flash else (0, 60, 255), 2)
    return frame

# ── Main Detection Loop ───────────────────────────────────────────────────────

def run_detection(source=0, signal_id: str = CAMERA_SIGNAL_ID):
    """
    Main loop: read frames → run YOLO → notify Flask → draw HUD.
    Fail-safe: continues even if Flask is unreachable.
    """
    print("=" * 60)
    print(f"  YOLOv8 Ambulance Detector v3")
    print(f"  Signal: {signal_id} | Flask: {FLASK_URL}")
    print("=" * 60)

    # Load model
    try:
        model = YOLO(MODEL_PATH)
        print(f"\n✓ Model loaded: {MODEL_PATH}")
        print(f"✓ Classes: {list(model.names.values())}")
    except Exception as e:
        print(f"\n✗ Model load failed: {e}")
        print("  Run python train.py first")
        return

    # Open video source
    try:
        src = int(source)
    except ValueError:
        src = source

    cap = cv2.VideoCapture(src, cv2.CAP_DSHOW if isinstance(src, int) else 0)
    if not cap.isOpened():
        print(f"\n✗ Cannot open source: {source}")
        return

    print(f"✓ Camera opened: {source}")
    print(f"\n  Q / ESC → quit  |  S → screenshot  |  +/- → confidence")
    print()

    conf_thresh   = CONF_THRESH
    frame_count   = 0
    fps           = 0.0
    fps_timer     = time.time()
    screenshot_n  = 0

    # Track consecutive ambulance detections for stability
    amb_frame_count = 0
    AMB_CONFIRM_FRAMES = 3  # require N consecutive frames before acting

    while True:
        ret, frame = cap.read()
        if not ret:
            print("✗ Frame read failed — retrying...")
            time.sleep(0.1)
            continue

        frame_count += 1
        if frame_count % 15 == 0:
            fps       = 15 / (time.time() - fps_timer)
            fps_timer = time.time()

        # ── YOLO Inference ────────────────────────────────────────────────────

        results = model(frame, conf=conf_thresh, iou=IOU_THRESH,
                        imgsz=IMG_SIZE, verbose=False)

        detections     = []
        is_ambulance   = False
        best_amb_conf  = 0.0
        best_amb_bbox  = []

        for result in results:
            if result.boxes is None: continue
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf_val  = float(box.conf[0])
                class_id  = int(box.cls[0])
                class_name = model.names[class_id]
                color      = get_color(class_name)

                draw_detection(frame, (x1, y1, x2, y2), class_name, conf_val, color)

                det = {
                    "label"     : class_name,
                    "confidence": round(conf_val, 3),
                    "bbox"      : [int(x1), int(y1), int(x2), int(y2)],
                    "center"    : [int((x1+x2)/2), int((y1+y2)/2)],
                }
                detections.append(det)

                # Track best ambulance detection
                if class_name.lower() == "ambulance" and conf_val > best_amb_conf:
                    is_ambulance  = True
                    best_amb_conf = conf_val
                    best_amb_bbox = [int(x1), int(y1), int(x2), int(y2)]

        # ── Stability Check ───────────────────────────────────────────────────

        if is_ambulance:
            amb_frame_count += 1
        else:
            amb_frame_count = max(0, amb_frame_count - 1)

        # Only act after N consecutive frames (reduces false positives)
        confirmed_ambulance = amb_frame_count >= AMB_CONFIRM_FRAMES

        # ── Notify Flask (background thread) ──────────────────────────────────

        threading.Thread(
            target=notify_flask_detection,
            args=(signal_id, confirmed_ambulance, best_amb_conf, best_amb_bbox),
            daemon=True,
        ).start()

        # ── HUD ───────────────────────────────────────────────────────────────

        draw_hud(frame, fps, detections, confirmed_ambulance, _flask_ok, signal_id)

        # Print to terminal every 15 frames
        if detections and frame_count % 15 == 0:
            print(f"\n[Frame {frame_count}] Signal: {signal_id}")
            for d in detections:
                icon = CLASS_ICONS.get(d["label"], "•")
                print(f"  {icon} {d['label']:12} conf={d['confidence']:.2f} "
                      f"bbox={d['bbox']}")
            if confirmed_ambulance:
                print(f"  ⚠  AMBULANCE CONFIRMED (conf={best_amb_conf:.2f})")

        cv2.imshow(f"Smart Ambulance Detector — {signal_id}", frame)

        # ── Key Controls ──────────────────────────────────────────────────────

        key = cv2.waitKey(1) & 0xFF
        if key in [ord("q"), 27]:
            print("\n→ Quitting...")
            # Notify Flask that camera is going offline
            notify_flask_detection(signal_id, False, 0.0, [])
            break
        elif key == ord("s"):
            screenshot_n += 1
            fname = f"shot_{signal_id}_{screenshot_n:03d}.jpg"
            cv2.imwrite(fname, frame)
            print(f"✓ Saved {fname}")
        elif key == ord("+"):
            conf_thresh = min(0.95, conf_thresh + 0.05)
            print(f"→ Confidence: {conf_thresh:.2f}")
        elif key == ord("-"):
            conf_thresh = max(0.05, conf_thresh - 0.05)
            print(f"→ Confidence: {conf_thresh:.2f}")

    cap.release()
    cv2.destroyAllWindows()
    print("✓ Detector stopped.")


def run_on_image(image_path: str, signal_id: str = CAMERA_SIGNAL_ID):
    """Run detection on a single image — useful for testing."""
    print(f"\n→ Detecting in: {image_path}")
    model  = YOLO(MODEL_PATH)
    result = model(image_path, conf=CONF_THRESH, iou=IOU_THRESH, imgsz=IMG_SIZE)
    out    = f"detected_{Path(image_path).name}"
    result[0].save(filename=out)
    print(f"✓ Saved: {out}")
    for box in result[0].boxes:
        label = model.names[int(box.cls[0])]
        conf  = float(box.conf[0])
        bbox  = [int(v) for v in box.xyxy[0].tolist()]
        print(f"  • {label:12} conf={conf:.2f} bbox={bbox}")
        if label.lower() == "ambulance":
            notify_flask_detection(signal_id, True, conf, bbox)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YOLOv8 Ambulance Detector v3")
    parser.add_argument("--source",    default="0",              help="Camera source (0=webcam, path=file)")
    parser.add_argument("--signal",    default=CAMERA_SIGNAL_ID, help="Signal node ID this camera covers")
    parser.add_argument("--model",     default=MODEL_PATH,       help="Path to best.pt weights")
    parser.add_argument("--flask",     default=FLASK_URL,        help="Flask server URL")
    parser.add_argument("--conf",      type=float, default=CONF_THRESH, help="Confidence threshold")
    args = parser.parse_args()

    MODEL_PATH  = args.model
    FLASK_URL   = args.flask
    CONF_THRESH = args.conf

    run_detection(source=args.source, signal_id=args.signal)