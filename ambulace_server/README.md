# 🚑 Smart Ambulance Traffic System — Flask Server

Python Flask backend with Dijkstra routing, dynamic traffic simulation, and ESP32 signal control.

---

## 📁 Structure

```
ambulance_server/
├── app.py              ← Main Flask server (all logic)
├── requirements.txt    ← Python dependencies
├── test_server.py      ← Endpoint test suite
└── README.md
```

---

## ⚙️ Setup

```bash
# 1. Create virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start server
python app.py
```

Server runs at: `http://0.0.0.0:5000`

---

## 🔌 API Endpoints

### `POST /ambulance`
Receive GPS ping from ambulance mobile app. When status is `active`, automatically computes best route and sends GREEN to all ESP32 signals along the path.

**Request:**
```json
{
  "ambulance_id": "AMB001",
  "lat": 28.6139,
  "lon": 77.2090,
  "status": "active"
}
```

**Response:**
```json
{
  "received": true,
  "route": ["HOSPITAL", "S1", "S4", "S5", "S6", "S9", "DEST"],
  "route_cost": 1820.5,
  "signals_cleared": ["S1", "S5", "S9"],
  "esp32_responses": [...],
  "traffic": { "S1": { "vehicle_count": 12, "congestion": "LOW" }, ... }
}
```

---

### `POST /route`
Compute best route between any two graph nodes.

**Request:**
```json
{
  "start": "HOSPITAL",
  "end": "DEST",
  "clear_signals": true
}
```

---

### `GET /status`
Full system status — ambulance position, current route, active GREEN signals.

---

### `GET /traffic`
Live vehicle counts on all signal nodes.

---

### `POST /traffic`
Manually update vehicle count (for sensor/AI integration).

```json
{ "signal_id": "S2", "vehicle_count": 75 }
```

---

### `POST /esp32/<signal_id>/green`
Send GREEN command to a specific ESP32 device.

```
POST /esp32/S1/green
```

---

## 🗺️ Traffic Graph

```
[HOSPITAL] ── S1 ── S2 ── S3
              |            |
             S4 ── S5 ── S6
                         |
            S7 ── S8 ── S9 ── [DEST]
```

Edge weights = base distance (meters) + traffic penalty (quadratic).

---

## 📡 ESP32 Configuration

Edit `SIGNALS` dict in `app.py`:

```python
SIGNALS = {
    "S1": {"vehicle_count": 12, "esp32_ip": "192.168.1.101", ...},
    "S2": {"vehicle_count": 30, "esp32_ip": "192.168.1.102", ...},
    ...
}
```

ESP32 receives: `GET http://192.168.1.101/?cmd=GREEN`

---

## 🧠 Dijkstra Algorithm

Weight formula per edge:
```
weight = base_distance + traffic_penalty(neighbor_vehicle_count)
penalty = 500 × (vehicle_count / 100)²
```

- 0 vehicles   → 0 penalty
- 50 vehicles  → 125 penalty  
- 100 vehicles → 500 penalty

This routes ambulances around heavily congested intersections automatically.

---

## 🧪 Run Tests

```bash
# Terminal 1 — start server
python app.py

# Terminal 2 — run tests
python test_server.py
```

---

## 🔗 Flutter App Integration

Replace `SERVER_IP` in Flutter `main.dart`:
```dart
static const String _serverUrl = 'http://YOUR_PC_IP:5000/ambulance';
```

Find your PC IP:
- Windows: `ipconfig`
- Mac/Linux: `ifconfig`

Both phone and PC must be on the **same Wi-Fi network**.