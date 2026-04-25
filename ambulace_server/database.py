"""
Smart Ambulance Backend — In-Memory Database Module
====================================================
Lightweight thread-safe storage for ambulances, trips, GPS history,
and YOLO detection logs. Persists to a SQLite file for durability.
"""

import os
import sqlite3
import threading
import time
from datetime import datetime
from typing import Optional

_DB_PATH = os.environ.get("AMBULANCE_DB", os.path.join(os.path.dirname(__file__), "ambulance.db"))
_lock = threading.Lock()


def _conn():
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def _init():
    with _lock, _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS ambulances (
            ambulance_id   TEXT PRIMARY KEY,
            reg_number     TEXT,
            hospital_name  TEXT,
            driver_name    TEXT,
            driver_phone   TEXT,
            vehicle_type   TEXT,
            status         TEXT DEFAULT 'inactive',
            created_at     TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS trips (
            trip_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ambulance_id   TEXT,
            origin_lat     REAL,
            origin_lon     REAL,
            dest_lat       REAL,
            dest_lon       REAL,
            route_signals  TEXT,
            passed_signals TEXT,
            distance_km    REAL,
            started_at     TEXT DEFAULT CURRENT_TIMESTAMP,
            ended_at       TEXT
        );

        CREATE TABLE IF NOT EXISTS gps_log (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            ambulance_id   TEXT,
            lat            REAL,
            lon            REAL,
            speed_kmh      REAL,
            trip_id        INTEGER,
            ts             TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS detections (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            ambulance_id   TEXT,
            confidence     REAL,
            bbox           TEXT,
            source         TEXT,
            lat            REAL,
            lon            REAL,
            ts             TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_gps_amb  ON gps_log(ambulance_id);
        CREATE INDEX IF NOT EXISTS idx_trip_amb ON trips(ambulance_id);
        """)
        # Seed a default ambulance if none exists
        cur = c.execute("SELECT COUNT(*) AS n FROM ambulances")
        if cur.fetchone()["n"] == 0:
            c.execute("""
                INSERT INTO ambulances
                (ambulance_id, reg_number, hospital_name, driver_name,
                 driver_phone, vehicle_type, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ("AMB001", "DL01-AB-1234", "City General Hospital",
                  "Rakesh Kumar", "+91-9876543210", "Type-B", "inactive"))


_init()


# ── Ambulances ────────────────────────────────────────────────────────────────

def register_ambulance(amb_id: str, reg_number: str, hospital: str,
                       driver: str = "", phone: str = "",
                       vtype: str = "Type-B") -> dict:
    with _lock, _conn() as c:
        c.execute("""
            INSERT OR REPLACE INTO ambulances
            (ambulance_id, reg_number, hospital_name, driver_name,
             driver_phone, vehicle_type, status)
            VALUES (?, ?, ?, ?, ?, ?, COALESCE(
                (SELECT status FROM ambulances WHERE ambulance_id=?),
                'inactive'))
        """, (amb_id, reg_number, hospital, driver, phone, vtype, amb_id))
    return get_ambulance(amb_id)


def get_ambulance(amb_id: str) -> dict:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM ambulances WHERE ambulance_id=?", (amb_id,)
        ).fetchone()
        return dict(row) if row else {}


def get_all_ambulances() -> list:
    with _conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM ambulances ORDER BY created_at DESC"
        ).fetchall()]


def update_ambulance_status(amb_id: str, status: str) -> None:
    with _lock, _conn() as c:
        c.execute(
            "UPDATE ambulances SET status=? WHERE ambulance_id=?",
            (status, amb_id))


# ── Trips ─────────────────────────────────────────────────────────────────────

def start_trip(amb_id: str, origin_lat: float, origin_lon: float,
               route_signals: list, distance_km: float = 0.0) -> int:
    with _lock, _conn() as c:
        cur = c.execute("""
            INSERT INTO trips
            (ambulance_id, origin_lat, origin_lon, route_signals, distance_km)
            VALUES (?, ?, ?, ?, ?)
        """, (amb_id, origin_lat, origin_lon,
              ",".join(route_signals or []), distance_km))
        return int(cur.lastrowid)


def end_trip(trip_id: int, amb_id: str, dest_lat: float, dest_lon: float,
             passed_signals: list) -> None:
    if not trip_id:
        return
    with _lock, _conn() as c:
        c.execute("""
            UPDATE trips
            SET dest_lat=?, dest_lon=?, passed_signals=?, ended_at=?
            WHERE trip_id=?
        """, (dest_lat, dest_lon, ",".join(passed_signals or []),
              datetime.utcnow().isoformat() + "Z", trip_id))


def get_trip_history(amb_id: str, limit: int = 10) -> list:
    with _conn() as c:
        return [dict(r) for r in c.execute("""
            SELECT * FROM trips
            WHERE ambulance_id=?
            ORDER BY started_at DESC LIMIT ?
        """, (amb_id, limit)).fetchall()]


# ── GPS log ───────────────────────────────────────────────────────────────────

def log_gps(amb_id: str, lat: float, lon: float, speed_kmh: float,
            trip_id: Optional[int] = None) -> None:
    with _lock, _conn() as c:
        c.execute("""
            INSERT INTO gps_log (ambulance_id, lat, lon, speed_kmh, trip_id)
            VALUES (?, ?, ?, ?, ?)
        """, (amb_id, lat, lon, speed_kmh, trip_id))


def get_gps_history(amb_id: str, limit: int = 50) -> list:
    with _conn() as c:
        return [dict(r) for r in c.execute("""
            SELECT lat, lon, speed_kmh, trip_id, ts
            FROM gps_log
            WHERE ambulance_id=?
            ORDER BY id DESC LIMIT ?
        """, (amb_id, limit)).fetchall()]


# ── YOLO detections ───────────────────────────────────────────────────────────

def log_detection(amb_id: str, confidence: float, bbox: list, source: str,
                  lat: float = 0.0, lon: float = 0.0) -> None:
    with _lock, _conn() as c:
        c.execute("""
            INSERT INTO detections
            (ambulance_id, confidence, bbox, source, lat, lon)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (amb_id, confidence, str(bbox), source, lat, lon))


# ── Aggregate stats ───────────────────────────────────────────────────────────

def get_stats() -> dict:
    with _conn() as c:
        total_amb   = c.execute("SELECT COUNT(*) AS n FROM ambulances").fetchone()["n"]
        active_amb  = c.execute("SELECT COUNT(*) AS n FROM ambulances WHERE status='active'").fetchone()["n"]
        total_trips = c.execute("SELECT COUNT(*) AS n FROM trips").fetchone()["n"]
        total_gps   = c.execute("SELECT COUNT(*) AS n FROM gps_log").fetchone()["n"]
        total_dets  = c.execute("SELECT COUNT(*) AS n FROM detections").fetchone()["n"]
        return {
            "total_ambulances": total_amb,
            "active_ambulances": active_amb,
            "total_trips": total_trips,
            "total_gps_pings": total_gps,
            "total_detections": total_dets,
        }
