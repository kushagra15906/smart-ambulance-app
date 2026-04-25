"""
Smart Ambulance Backend — Real GPS Route + Signal Control
=========================================================
Flask server that controls ESP32 traffic signals along an ambulance's
real-time route. Supports:
  - Real GPS from mobile app (every 2s)
  - Dynamic green-corridor scheduling
  - Parallel ESP32 control (GREEN/RED/STOP/RESET)
  - YOLO camera confirmation
  - Traffic prediction & congestion levels
"""

import logging
import math
import os
import random
import threading
import time
from datetime import datetime

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

import database as db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# ── Constants ─────────────────────────────────────────────────────────────────

ESP32_TIMEOUT    = 2          # seconds for ESP32 HTTP requests
MAX_VEHICLES     = 100
GREEN_RADIUS_M   = 300        # GREEN signals within 300m of ambulance
PASSED_RADIUS_M  = 100        # signal considered passed when 100m+ behind
AVG_SPEED_MPS    = 10.0       # ~36 km/h city default
GREEN_NOW_ETA    = 30         # seconds: turn GREEN immediately
SCHEDULE_ETA     = 120        # seconds: schedule GREEN

# ── Signal Nodes (ESP32 devices) ──────────────────────────────────────────────
# Replace lat/lon and esp32_ip with the real values for your hardware.

SIGNALS = {
    "S1": {"vehicle_count": 12, "is_green": False, "is_stopped": False,
           "esp32_ip": "192.168.1.101",
           "lat": 28.6150, "lon": 77.2100,
           "location_name": "Signal 1 - Main Road",
           "current_phase": "RED"},
    "S2": {"vehicle_count": 30, "is_green": False, "is_stopped": False,
           "esp32_ip": "192.168.1.102",
           "lat": 28.6200, "lon": 77.2150,
           "location_name": "Signal 2 - Junction A",
           "current_phase": "RED"},
    "S3": {"vehicle_count": 8,  "is_green": False, "is_stopped": False,
           "esp32_ip": "192.168.1.103",
           "lat": 28.6250, "lon": 77.2200,
           "location_name": "Signal 3 - Crossing B",
           "current_phase": "RED"},
    "S4": {"vehicle_count": 45, "is_green": False, "is_stopped": False,
           "esp32_ip": "192.168.1.104",
           "lat": 28.6300, "lon": 77.2250,
           "location_name": "Signal 4 - Highway Entry",
           "current_phase": "RED"},
    "S5": {"vehicle_count": 20, "is_green": False, "is_stopped": False,
           "esp32_ip": "192.168.1.105",
           "lat": 28.6350, "lon": 77.2300,
           "location_name": "Signal 5 - Market Road",
           "current_phase": "RED"},
    "S6": {"vehicle_count": 60, "is_green": False, "is_stopped": False,
           "esp32_ip": "192.168.1.106",
           "lat": 28.6400, "lon": 77.2350,
           "location_name": "Signal 6 - Central Square",
           "current_phase": "RED"},
}

_lock = threading.Lock()

# ── Ambulance live state ──────────────────────────────────────────────────────

ambulance = {
    "id"             : None,
    "lat"            : None,
    "lon"            : None,
    "speed_mps"      : AVG_SPEED_MPS,
    "status"         : "inactive",
    "last_gps_time"  : None,
    "dest_lat"       : None,
    "dest_lon"       : None,
    "dest_name"      : "",
    "distance_text"  : "",
    "duration_text"  : "",
    "trip_id"        : None,
    "passed_signals" : set(),
    "active_signals" : [],
}

# YOLO state per signal
yolo_state = {s: {"detected": False, "confidence": 0.0, "last_seen": None}
              for s in SIGNALS}

# Vehicle-count history (for weighted moving average prediction)
_traffic_history = {s: [SIGNALS[s]["vehicle_count"]] * 5 for s in SIGNALS}


# ── Utilities ─────────────────────────────────────────────────────────────────

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two GPS points."""
    R  = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a  = (math.sin(dp / 2) ** 2
          + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _now() -> float:
    return time.time()


def _ts() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _congestion(c: float) -> str:
    if c < 20: return "LOW"
    if c < 50: return "MEDIUM"
    if c < 75: return "HIGH"
    return "CRITICAL"


def _predict_traffic(sig_id: str) -> float:
    """Weighted moving average: recent samples weigh more."""
    hist = _traffic_history.get(sig_id, [])
    if not hist:
        return 0.0
    weights = list(range(1, len(hist) + 1))
    total_w = sum(weights)
    return round(sum(v * w for v, w in zip(hist, weights)) / total_w, 1)


# ── ESP32 Control ─────────────────────────────────────────────────────────────

def _send_esp32(sig_id: str, cmd: str) -> dict:
    """
    Send command to one ESP32 traffic light.
    cmd: GREEN | RED | STOP | RESET
    Falls back to local simulation if hardware is unreachable.
    """
    if sig_id not in SIGNALS:
        return {"signal": sig_id, "success": False, "error": "unknown signal"}

    esp_ip = SIGNALS[sig_id]["esp32_ip"]
    url    = f"http://{esp_ip}/?cmd={cmd}"

    try:
        resp = requests.get(url, timeout=ESP32_TIMEOUT)
        ok   = resp.status_code == 200
        with _lock:
            SIGNALS[sig_id]["is_green"]      = (cmd == "GREEN" and ok)
            SIGNALS[sig_id]["is_stopped"]    = (cmd == "STOP"  and ok)
            if ok:
                SIGNALS[sig_id]["current_phase"] = cmd
        log.info("[ESP32] %s -> %s | %s", sig_id, cmd, "OK" if ok else "FAIL")
        return {"signal": sig_id, "cmd": cmd, "success": ok, "esp32_ip": esp_ip}
    except (requests.exceptions.ConnectionError,
            requests.exceptions.Timeout):
        # Simulate locally when no hardware is reachable
        with _lock:
            SIGNALS[sig_id]["is_green"]      = (cmd == "GREEN")
            SIGNALS[sig_id]["is_stopped"]    = (cmd == "STOP")
            SIGNALS[sig_id]["current_phase"] = cmd
        log.info("[SIM]   %s -> %s | (no hardware)", sig_id, cmd)
        return {"signal": sig_id, "cmd": cmd, "success": True,
                "note": "simulated (no hardware)"}
    except Exception as exc:
        return {"signal": sig_id, "cmd": cmd, "success": False, "error": str(exc)}


def _send_parallel(signal_ids: list, cmd: str) -> list:
    """Send command to multiple ESP32 devices simultaneously using threads."""
    results, rlock = [], threading.Lock()

    def _worker(s):
        r = _send_esp32(s, cmd)
        with rlock:
            results.append(r)

    threads = [threading.Thread(target=_worker, args=(s,), daemon=True)
               for s in signal_ids if s in SIGNALS]
    for t in threads: t.start()
    for t in threads: t.join(timeout=ESP32_TIMEOUT + 1)
    return results


# ── Route / Corridor logic ────────────────────────────────────────────────────

def _signals_near_ambulance(amb_lat: float, amb_lon: float,
                            radius_m: float = GREEN_RADIUS_M) -> list:
    """All signal IDs within radius_m of ambulance, sorted by distance."""
    nearby = []
    for sig_id, sig in SIGNALS.items():
        d = _haversine(amb_lat, amb_lon, sig["lat"], sig["lon"])
        if d <= radius_m:
            nearby.append((sig_id, d))
    nearby.sort(key=lambda x: x[1])
    return [s for s, _ in nearby]


def _signals_between(amb_lat: float, amb_lon: float,
                     dest_lat: float, dest_lon: float,
                     tolerance_factor: float = 1.4) -> list:
    """
    Signals roughly between ambulance and destination.
    A signal is 'on route' if going via it is no more than
    `tolerance_factor` longer than the direct path AND it's
    closer to the destination than the ambulance is.
    Returned ordered by distance from ambulance (closest first).
    """
    if dest_lat is None or dest_lon is None:
        return []
    candidates = []
    total = _haversine(amb_lat, amb_lon, dest_lat, dest_lon)
    if total <= 1:
        return []

    for sig_id, sig in SIGNALS.items():
        d_amb  = _haversine(amb_lat, amb_lon, sig["lat"], sig["lon"])
        d_dest = _haversine(sig["lat"], sig["lon"], dest_lat, dest_lon)
        if (d_amb + d_dest) <= (total * tolerance_factor) and d_dest < total:
            candidates.append((sig_id, d_amb))

    candidates.sort(key=lambda x: x[1])
    return [s for s, _ in candidates]


def _control_corridor(amb_lat: float, amb_lon: float,
                      dest_lat: float, dest_lon: float,
                      speed: float, trip_id, amb_id: str) -> dict:
    """
    Main corridor logic:
      • Signals on route within 30s ETA       -> GREEN now
      • Signals on route 30-120s ETA          -> schedule GREEN
      • Signals NOT on route                  -> STOP
      • Signals already passed by ambulance   -> RESET
    """
    route_sigs = _signals_between(amb_lat, amb_lon, dest_lat, dest_lon)
    all_sigs   = set(SIGNALS.keys())
    route_set  = set(route_sigs)
    cross_sigs = list(all_sigs - route_set)

    green_now, scheduled = [], []

    for sig_id in route_sigs:
        if sig_id in ambulance["passed_signals"]:
            continue
        sig  = SIGNALS[sig_id]
        dist = _haversine(amb_lat, amb_lon, sig["lat"], sig["lon"])
        eta  = dist / max(speed, 1.0)

        if eta < GREEN_NOW_ETA:
            green_now.append(sig_id)
        elif eta < SCHEDULE_ETA:
            scheduled.append((sig_id, eta))

    # 1. STOP all crossing signals immediately
    if cross_sigs:
        log.info("[CORRIDOR] STOP crossing: %s", cross_sigs)
        threading.Thread(target=_send_parallel,
                         args=(cross_sigs, "STOP"), daemon=True).start()

    # 2. GREEN signals close enough
    if green_now:
        log.info("[CORRIDOR] GREEN now: %s", green_now)
        threading.Thread(target=_send_parallel,
                         args=(green_now, "GREEN"), daemon=True).start()
        with _lock:
            ambulance["active_signals"] = green_now

    # 3. Schedule GREEN for farther signals (turn GREEN ~25s before arrival)
    for sig_id, eta in scheduled:
        delay = max(0.0, eta - 25.0)

        def _delayed(s=sig_id, d=delay):
            time.sleep(d)
            if (ambulance["status"] == "active"
                    and s not in ambulance["passed_signals"]):
                log.info("[CORRIDOR] Scheduled GREEN -> %s", s)
                _send_esp32(s, "GREEN")

        threading.Thread(target=_delayed, daemon=True).start()
        log.info("[CORRIDOR] Schedule GREEN in %.0fs -> %s", delay, sig_id)

    # 4. RESET signals the ambulance has passed
    for sig_id in list(ambulance["passed_signals"]):
        sig = SIGNALS.get(sig_id)
        if not sig: continue
        d = _haversine(amb_lat, amb_lon, sig["lat"], sig["lon"])
        if d > PASSED_RADIUS_M * 2:
            threading.Thread(target=_send_esp32,
                             args=(sig_id, "RESET"), daemon=True).start()

    # 5. Detect newly-passed signals (those very close, then we'll move past)
    for sig_id in route_sigs:
        sig = SIGNALS[sig_id]
        d = _haversine(amb_lat, amb_lon, sig["lat"], sig["lon"])
        if d < PASSED_RADIUS_M:
            with _lock:
                ambulance["passed_signals"].add(sig_id)

    return {
        "route_signals": route_sigs,
        "green_now"    : green_now,
        "scheduled"    : [s for s, _ in scheduled],
        "cross_stopped": cross_sigs,
    }


# ── Background traffic simulation ─────────────────────────────────────────────

def _simulate():
    while True:
        time.sleep(10)
        with _lock:
            for sid, sig in SIGNALS.items():
                if not sig["is_green"] and not sig["is_stopped"]:
                    sig["vehicle_count"] = max(0, min(
                        MAX_VEHICLES,
                        sig["vehicle_count"] + random.randint(-8, 8)))
                _traffic_history[sid].append(sig["vehicle_count"])
                if len(_traffic_history[sid]) > 12:
                    _traffic_history[sid].pop(0)


threading.Thread(target=_simulate, daemon=True).start()


# ── Snapshot helper ───────────────────────────────────────────────────────────

def _traffic_snapshot() -> dict:
    with _lock:
        return {
            sid: {
                "vehicle_count"    : s["vehicle_count"],
                "is_green"         : s["is_green"],
                "is_stopped"       : s["is_stopped"],
                "current_phase"    : s["current_phase"],
                "congestion"       : _congestion(s["vehicle_count"]),
                "location_name"    : s["location_name"],
                "lat"              : s["lat"],
                "lon"              : s["lon"],
                "esp32_ip"         : s["esp32_ip"],
                "predicted_traffic": _predict_traffic(sid),
            }
            for sid, s in SIGNALS.items()
        }


# ═══════════════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/set-route", methods=["POST"])
def set_route():
    """Start ambulance mode with origin + destination GPS."""
    data      = request.get_json(silent=True) or {}
    amb_id    = data.get("ambulance_id", "AMB001")
    orig_lat  = float(data.get("origin_lat", 0))
    orig_lon  = float(data.get("origin_lon", 0))
    dest_lat  = float(data.get("dest_lat",   0))
    dest_lon  = float(data.get("dest_lon",   0))
    dest_name = data.get("dest_name", "")
    dist_text = data.get("distance_text", "")
    dur_text  = data.get("duration_text",  "")

    db.get_ambulance(amb_id)  # ensure exists / log access

    route_sigs = _signals_between(orig_lat, orig_lon, dest_lat, dest_lon)
    trip_id    = db.start_trip(amb_id, orig_lat, orig_lon, route_sigs, 0)

    with _lock:
        ambulance.update({
            "id"            : amb_id,
            "lat"           : orig_lat,
            "lon"           : orig_lon,
            "status"        : "active",
            "dest_lat"      : dest_lat,
            "dest_lon"      : dest_lon,
            "dest_name"     : dest_name,
            "distance_text" : dist_text,
            "duration_text" : dur_text,
            "trip_id"       : trip_id,
            "passed_signals": set(),
            "last_gps_time" : _now(),
        })

    db.update_ambulance_status(amb_id, "active")
    log.info("[SET-ROUTE] %s -> %s | signals on route: %s",
             f"{orig_lat:.4f},{orig_lon:.4f}", dest_name, route_sigs)

    threading.Thread(
        target=_control_corridor,
        args=(orig_lat, orig_lon, dest_lat, dest_lon,
              AVG_SPEED_MPS, trip_id, amb_id),
        daemon=True,
    ).start()

    signal_details = []
    for sig_id in route_sigs:
        sig = SIGNALS[sig_id]
        d   = _haversine(orig_lat, orig_lon, sig["lat"], sig["lon"])
        signal_details.append({
            "signal_id"    : sig_id,
            "location"     : sig["location_name"],
            "lat"          : sig["lat"],
            "lon"          : sig["lon"],
            "distance_m"   : round(d),
            "vehicle_count": sig["vehicle_count"],
            "congestion"   : _congestion(sig["vehicle_count"]),
        })

    return jsonify({
        "route_set"       : True,
        "ambulance_id"    : amb_id,
        "trip_id"         : trip_id,
        "origin"          : {"lat": orig_lat, "lon": orig_lon},
        "destination"     : {"lat": dest_lat, "lon": dest_lon, "name": dest_name},
        "distance"        : dist_text,
        "duration"        : dur_text,
        "signals_on_route": route_sigs,
        "signal_details"  : signal_details,
        "total_signals"   : len(route_sigs),
        "timestamp"       : _ts(),
    }), 200


@app.route("/update-location", methods=["POST"])
def update_location():
    """Live GPS every 2 seconds — re-runs corridor control dynamically."""
    data   = request.get_json(silent=True) or {}
    amb_id = data.get("ambulance_id", "AMB001")
    lat    = float(data.get("lat", 0))
    lon    = float(data.get("lon", 0))
    speed  = float(data.get("speed_mps", AVG_SPEED_MPS))

    with _lock:
        ambulance.update({
            "lat"          : lat,
            "lon"          : lon,
            "speed_mps"    : max(speed, 1.0),
            "last_gps_time": _now(),
        })

    db.log_gps(amb_id, lat, lon, speed * 3.6, ambulance.get("trip_id"))

    if ambulance["status"] != "active":
        return jsonify({"status": "inactive", "timestamp": _ts()}), 200

    dest_lat = ambulance.get("dest_lat") or 0
    dest_lon = ambulance.get("dest_lon") or 0
    if dest_lat == 0 and dest_lon == 0:
        return jsonify({"status": "no_destination", "timestamp": _ts()}), 200

    corridor = _control_corridor(
        lat, lon, dest_lat, dest_lon,
        ambulance["speed_mps"], ambulance.get("trip_id"), amb_id,
    )

    return jsonify({
        "lat"           : lat,
        "lon"           : lon,
        "signals_green" : corridor["green_now"],
        "route_signals" : corridor["route_signals"],
        "scheduled"     : corridor["scheduled"],
        "cross_stopped" : corridor["cross_stopped"],
        "passed_signals": list(ambulance["passed_signals"]),
        "timestamp"     : _ts(),
    }), 200


@app.route("/ambulance", methods=["POST"])
def receive_ambulance():
    """Legacy endpoint — GPS ping or deactivate (resets all signals)."""
    data   = request.get_json(silent=True) or {}
    amb_id = data.get("ambulance_id", "AMB001")
    lat    = float(data.get("lat", 0))
    lon    = float(data.get("lon", 0))
    status = data.get("status", "inactive").lower()
    speed  = float(data.get("speed", 0)) / 3.6

    amb_info = db.get_ambulance(amb_id)

    with _lock:
        ambulance.update({
            "id": amb_id, "lat": lat, "lon": lon,
            "speed_mps": max(speed, 1.0),
            "status": status, "last_gps_time": _now(),
        })

    db.update_ambulance_status(amb_id, status)
    db.log_gps(amb_id, lat, lon, speed * 3.6, ambulance.get("trip_id"))

    payload = {
        "received": True, "ambulance_id": amb_id,
        "reg_number": amb_info.get("reg_number") if amb_info else None,
        "status": status, "traffic": _traffic_snapshot(),
        "timestamp": _ts(),
    }

    if status == "inactive":
        trip_id = ambulance.get("trip_id")
        if trip_id:
            db.end_trip(trip_id, amb_id, lat, lon,
                        list(ambulance.get("passed_signals", set())))
        all_sigs = list(SIGNALS.keys())
        threading.Thread(target=_send_parallel,
                         args=(all_sigs, "RESET"), daemon=True).start()
        with _lock:
            ambulance.update({
                "status": "inactive", "trip_id": None,
                "passed_signals": set(), "active_signals": [],
                "dest_lat": None, "dest_lon": None,
            })
            for s in SIGNALS.values():
                s.update({"is_green": False, "is_stopped": False,
                          "current_phase": "RED"})
        payload["signals_reset"] = all_sigs
        log.info("[DEACTIVATE] All signals reset to normal")

    return jsonify(payload), 200


@app.route("/detection", methods=["POST"])
def yolo_detection():
    """YOLO camera input — confirms ambulance presence and forces GREEN."""
    data       = request.get_json(silent=True) or {}
    sig_id     = data.get("signal_id")
    detected   = bool(data.get("detected", False))
    confidence = float(data.get("confidence", 0.0))
    vc         = int(data.get("vehicle_count", 0))
    amb_id     = data.get("ambulance_id", "CAM001")

    if sig_id not in SIGNALS:
        return jsonify({"error": f"Unknown signal: {sig_id}"}), 400

    with _lock:
        yolo_state[sig_id].update({
            "detected"  : detected,
            "confidence": confidence,
            "last_seen" : _now() if detected else yolo_state[sig_id]["last_seen"],
        })
        if vc > 0:
            SIGNALS[sig_id]["vehicle_count"] = min(vc, MAX_VEHICLES)

    action = "NONE"

    if detected and confidence >= 0.45:
        log.info("[YOLO] Ambulance at %s conf=%.2f -> GREEN",
                 sig_id, confidence)
        _send_esp32(sig_id, "GREEN")
        action = "GREEN"

        # Stop crossing signals (those not on route)
        dest_lat = ambulance.get("dest_lat") or 0
        dest_lon = ambulance.get("dest_lon") or 0
        sig_lat  = SIGNALS[sig_id]["lat"]
        sig_lon  = SIGNALS[sig_id]["lon"]
        amb_lat  = ambulance.get("lat") or sig_lat
        amb_lon  = ambulance.get("lon") or sig_lon

        route_sigs = (set(_signals_between(amb_lat, amb_lon,
                                           dest_lat, dest_lon))
                      if dest_lat else {sig_id})
        cross = [s for s in SIGNALS if s != sig_id and s not in route_sigs]
        if cross:
            threading.Thread(target=_send_parallel,
                             args=(cross, "STOP"), daemon=True).start()
            action = "GREEN+STOP_CROSSING"

    elif not detected and SIGNALS[sig_id]["is_green"]:
        # Ambulance has left this signal — reset to normal
        _send_esp32(sig_id, "RESET")
        action = "RESET"
        with _lock:
            ambulance.setdefault("passed_signals", set()).add(sig_id)

    lat = ambulance.get("lat") or SIGNALS[sig_id]["lat"]
    lon = ambulance.get("lon") or SIGNALS[sig_id]["lon"]
    db.log_detection(amb_id, confidence, data.get("bbox", []),
                     "yolo_camera", lat, lon)

    return jsonify({
        "signal_id"   : sig_id,
        "detected"    : detected,
        "confidence"  : confidence,
        "action_taken": action,
        "signal_state": SIGNALS[sig_id]["current_phase"],
        "timestamp"   : _ts(),
    }), 200


@app.route("/signal-control", methods=["POST"])
def signal_control():
    """Manual override — GREEN | RED | STOP | RESET on one or many signals."""
    data    = request.get_json(silent=True) or {}
    targets = ([data["signal_id"]] if "signal_id" in data
               else data.get("signal_ids", []))
    cmd     = data.get("cmd", "GREEN").upper()
    if cmd not in {"GREEN", "RED", "STOP", "RESET"}:
        return jsonify({"error": "Invalid cmd"}), 400
    if not targets:
        return jsonify({"error": "No signal_id(s) provided"}), 400
    results = _send_parallel(targets, cmd)
    return jsonify({"cmd": cmd, "results": results,
                    "timestamp": _ts()}), 200


@app.route("/traffic", methods=["GET"])
def get_traffic():
    """Current + predicted traffic for all signals."""
    snap = _traffic_snapshot()
    avg  = sum(snap[s]["vehicle_count"] for s in snap) / max(len(snap), 1)
    return jsonify({
        "signals"       : snap,
        "average_count" : round(avg, 1),
        "overall_status": _congestion(int(avg)),
        "timestamp"     : _ts(),
    }), 200


@app.route("/traffic", methods=["POST"])
def update_traffic():
    """Update vehicle count for one signal (e.g. from camera-counting)."""
    data  = request.get_json(silent=True) or {}
    sid   = data.get("signal_id")
    count = data.get("vehicle_count")
    if sid not in SIGNALS or count is None or int(count) < 0:
        return jsonify({"error": "Invalid input"}), 400
    with _lock:
        SIGNALS[sid]["vehicle_count"] = min(int(count), MAX_VEHICLES)
    return jsonify({"updated": True, "signal_id": sid,
                    "vehicle_count": SIGNALS[sid]["vehicle_count"]}), 200


@app.route("/status", methods=["GET"])
def get_status():
    with _lock:
        state = {k: v for k, v in ambulance.items() if k != "passed_signals"}
        state["passed_signals"] = list(ambulance.get("passed_signals", set()))
    return jsonify({
        "system"         : "Smart Ambulance v6 - Real GPS Routing",
        "ambulance"      : state,
        "active_greens"  : sum(1 for s in SIGNALS.values() if s["is_green"]),
        "stopped_signals": sum(1 for s in SIGNALS.values() if s["is_stopped"]),
        "signal_count"   : len(SIGNALS),
        "stats"          : db.get_stats(),
        "timestamp"      : _ts(),
    }), 200


@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    miss = [k for k in ("ambulance_id", "reg_number", "hospital_name")
            if k not in data]
    if miss:
        return jsonify({"error": f"Missing: {miss}"}), 400
    amb = db.register_ambulance(
        data["ambulance_id"], data["reg_number"], data["hospital_name"],
        data.get("driver_name", ""), data.get("driver_phone", ""),
        data.get("vehicle_type", "Type-B"))
    return jsonify({"registered": True, "ambulance": amb}), 200


@app.route("/ambulances", methods=["GET"])
def list_ambulances():
    return jsonify({"ambulances": db.get_all_ambulances()}), 200


@app.route("/ambulance/<amb_id>", methods=["GET"])
def get_ambulance_details(amb_id):
    info = db.get_ambulance(amb_id)
    if not info:
        return jsonify({"error": "Not found"}), 404
    return jsonify({
        "ambulance"  : info,
        "gps_history": db.get_gps_history(amb_id, 50),
        "trips"      : db.get_trip_history(amb_id, 10),
    }), 200


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "name"    : "Smart Ambulance Backend - Real GPS Routing",
        "version" : "1.0.0",
        "how_it_works": [
            "1. Mobile app sends GPS origin + destination to /set-route",
            "2. Backend identifies ESP32 signals on the route",
            "3. Signals within 30s ETA -> GREEN immediately",
            "4. Signals 30-120s ETA   -> scheduled GREEN",
            "5. Crossing signals      -> STOP",
            "6. /update-location every 2s adjusts the corridor dynamically",
            "7. YOLO detections at /detection force GREEN on confirmation",
            "8. Passed signals -> RESET automatically",
        ],
        "endpoints": {
            "POST /set-route"      : "Start ambulance mode with origin + destination",
            "POST /update-location": "Live GPS (every 2s) -> dynamic signal control",
            "POST /detection"      : "YOLO camera result",
            "POST /signal-control" : "Manual signal override",
            "POST /ambulance"      : "Legacy GPS ping / deactivate",
            "POST /register"       : "Register an ambulance",
            "POST /traffic"        : "Push vehicle-count update for one signal",
            "GET  /traffic"        : "Current + predicted traffic for all signals",
            "GET  /status"         : "Full system status",
            "GET  /ambulances"     : "List all registered ambulances",
            "GET  /ambulance/<id>" : "Ambulance details + GPS history + trips",
        },
        "signals": list(SIGNALS.keys()),
        "timestamp": _ts(),
    }), 200


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal error"}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    log.info("=" * 60)
    log.info("  Smart Ambulance Backend - Real GPS Routing")
    log.info("  Signals: %d ESP32 devices configured", len(SIGNALS))
    log.info("  Listening on port %d", port)
    log.info("=" * 60)
    app.run(host="0.0.0.0", port=port, threaded=True, debug=False)
