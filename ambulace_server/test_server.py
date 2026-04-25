"""
test_server.py — Quick test suite for the Smart Ambulance Traffic Server
Run AFTER starting app.py:  python test_server.py
"""

import json
import sys
import time
import requests

BASE = "http://localhost:5000"
PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
SEP  = "-" * 55

def check(label: str, resp: requests.Response, expected_status: int = 200) -> dict:
    ok = resp.status_code == expected_status
    symbol = PASS if ok else FAIL
    print(f"  {symbol} [{resp.status_code}] {label}")
    data = resp.json()
    if not ok:
        print(f"       └─ {data}")
    return data

def section(title: str):
    print(f"\n{SEP}\n  {title}\n{SEP}")

# ── Tests ─────────────────────────────────────────────────────────────────────

section("1. API Root")
r = requests.get(f"{BASE}/")
d = check("GET /  →  API docs", r)
print(f"     Nodes: {d.get('graph_nodes')}")

section("2. Traffic Status")
r = requests.get(f"{BASE}/traffic")
d = check("GET /traffic  →  live signal data", r)
print(f"     Overall: {d.get('overall_status')} | Avg vehicles: {d.get('average_vehicle_count')}")

section("3. Update Traffic")
r = requests.post(f"{BASE}/traffic",
    json={"signal_id": "S2", "vehicle_count": 80})
d = check("POST /traffic  →  set S2 = 80 vehicles", r)
print(f"     S2 congestion: {d.get('congestion')}")

section("4. Route Computation")
r = requests.post(f"{BASE}/route",
    json={"start": "HOSPITAL", "end": "DEST", "clear_signals": False})
d = check("POST /route  →  HOSPITAL → DEST", r)
print(f"     Route: {' → '.join(d.get('route', []))}")
print(f"     Cost:  {d.get('route_cost')}")
print(f"     Hops:  {d.get('hop_count')}")
for node in d.get("route_details", []):
    print(f"       {node['node']:12} | {str(node.get('vehicle_count','-')):>4} vehicles | {node.get('congestion','')}")

section("5. Ambulance STANDBY Ping")
r = requests.post(f"{BASE}/ambulance",
    json={"ambulance_id": "AMB001", "lat": 28.6139, "lon": 77.2090, "status": "inactive"})
d = check("POST /ambulance  →  inactive ping", r)
print(f"     Traffic snapshot received: {'yes' if d.get('traffic') else 'no'}")

section("6. Ambulance ACTIVE Ping (triggers routing + ESP32)")
r = requests.post(f"{BASE}/ambulance",
    json={"ambulance_id": "AMB001", "lat": 28.6150, "lon": 77.2105, "status": "active"})
d = check("POST /ambulance  →  active ping", r)
print(f"     Route computed: {' → '.join(d.get('route', []))}")
print(f"     Route cost:     {d.get('route_cost')}")
print(f"     Signals cleared (attempted): {d.get('signals_cleared', [])}")
print(f"     ESP32 responses:")
for r32 in d.get("esp32_responses", []):
    icon = PASS if r32.get("success") else FAIL
    print(f"       {icon} {r32['signal']} ({r32.get('esp32_ip')}) — {r32.get('error', 'OK')}")

section("7. System Status")
r = requests.get(f"{BASE}/status")
d = check("GET /status  →  full system state", r)
amb = d.get("ambulance", {})
print(f"     Ambulance: {amb.get('ambulance_id')} | status={amb.get('status')}")
print(f"     Route: {amb.get('current_route')}")
print(f"     Active GREENs: {d.get('active_greens')}")

section("8. Manual ESP32 GREEN")
r = requests.post(f"{BASE}/esp32/S1/green")
d = check("POST /esp32/S1/green  →  manual override", r, expected_status=None)

section("9. Error Cases")
r = requests.post(f"{BASE}/route", json={"start": "NOWHERE", "end": "DEST"})
check("POST /route  →  invalid node", r, 400)
r = requests.post(f"{BASE}/ambulance", json={"lat": 28.0})
check("POST /ambulance  →  missing fields", r, 400)
r = requests.get(f"{BASE}/nonexistent")
check("GET /nonexistent  →  404 handler", r, 404)

print(f"\n{SEP}")
print("  All tests complete.")
print(f"{SEP}\n")