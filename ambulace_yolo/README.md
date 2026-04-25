# 🚑 YOLOv8 Ambulance Detection — Complete Guide

---

## 📁 Project Structure

```
ambulance_yolo/
├── train.py              ← Training script
├── detect.py             ← Real-time webcam detection
├── requirements.txt      ← Python packages
├── dataset/
│   ├── data.yaml         ← auto-created by train.py
│   ├── images/
│   │   ├── train/        ← put training images here
│   │   └── val/          ← put validation images here
│   └── labels/
│       ├── train/        ← YOLO format labels (.txt)
│       └── val/          ← YOLO format labels (.txt)
└── runs/
    └── train/
        └── ambulance_detector/
            └── weights/
                ├── best.pt    ← use this for detection
                └── last.pt
```

---

## STEP 1 — Install Python Packages

```bash
pip install -r requirements.txt
```

Or install manually:
```bash
pip install ultralytics opencv-python torch torchvision PyYAML
```

---

## STEP 2 — Get Dataset (3 Options)

### Option A — Roboflow (EASIEST — Recommended for beginners)

1. Go to https://roboflow.com → Sign up free
2. Click **"Create New Project"**
3. Project type: **Object Detection**
4. Upload your ambulance/car/truck images
5. Label them (draw boxes, assign class names)
6. Click **"Generate"** → choose **YOLOv8** format
7. Click **"Download"** → copy the download code

It gives you a snippet like:
```python
from roboflow import Roboflow
rf = Roboflow(api_key="YOUR_KEY")
project = rf.workspace("your-workspace").project("ambulance-detection")
dataset = project.version(1).download("yolov8")
```

Run that code → dataset downloaded automatically!

---

### Option B — LabelImg (Label your own images)

**Install:**
```bash
pip install labelImg
labelImg
```

**Steps:**
1. Open LabelImg
2. Click "Open Dir" → select folder with your images
3. Click "Change Save Dir" → select your labels folder
4. Press W → draw bounding box → type class name (ambulance/car/truck)
5. Press Ctrl+S to save
6. Press D for next image
7. Repeat for all images

**Label format:** Make sure it saves as **YOLO format** (not Pascal VOC)
- In LabelImg: View → check "YOLO" format

---

### Option C — Download Free Dataset

Use these free datasets from Roboflow Universe:
```
https://universe.roboflow.com/search?q=ambulance
```

Popular ones:
- "Ambulance Detection" by various creators
- Download in YOLOv8 format directly

---

## STEP 3 — Organize Dataset

After labeling, your folder should look like:

```
dataset/
├── images/
│   ├── train/
│   │   ├── ambulance_001.jpg
│   │   ├── car_001.jpg
│   │   └── truck_001.jpg
│   └── val/
│       ├── ambulance_val_001.jpg
│       └── car_val_001.jpg
└── labels/
    ├── train/
    │   ├── ambulance_001.txt   ← same name as image
    │   ├── car_001.txt
    │   └── truck_001.txt
    └── val/
        ├── ambulance_val_001.txt
        └── car_val_001.txt
```

**Each .txt label file contains (YOLO format):**
```
class_id center_x center_y width height
```
Example (ambulance = class 0, values normalized 0-1):
```
0 0.512 0.423 0.310 0.280
```

**Recommended dataset size:**
| Class | Min Images |
|---|---|
| Ambulance | 200+ |
| Car | 200+ |
| Truck | 100+ |

---

## STEP 4 — data.yaml File

The `data.yaml` file is auto-created by `train.py`. It looks like:

```yaml
path: /absolute/path/to/dataset
train: images/train
val: images/val
nc: 3
names:
  - ambulance
  - car
  - truck
```

Make sure class names match exactly what you used in LabelImg/Roboflow.

---

## STEP 5 — Train the Model

```bash
python train.py
```

**What happens:**
- Downloads YOLOv8 nano model (~6MB)
- Trains for 50 epochs
- Saves best weights to `runs/train/ambulance_detector/weights/best.pt`
- Shows training plots (loss, mAP)

**Training time estimates:**
| Hardware | Time for 50 epochs |
|---|---|
| CPU (i5/i7) | 2-5 hours |
| GPU (GTX 1060) | 20-40 minutes |
| GPU (RTX 3060) | 10-20 minutes |
| Google Colab (free) | 30-60 minutes |

---

## STEP 6 — Train on Google Colab (FREE GPU)

If your PC is slow, use Google Colab:

1. Go to https://colab.research.google.com
2. Create new notebook
3. Go to **Runtime → Change runtime type → GPU**
4. Paste and run:

```python
# Install
!pip install ultralytics roboflow

# Download dataset from Roboflow
from roboflow import Roboflow
rf = Roboflow(api_key="YOUR_KEY")
project = rf.workspace().project("ambulance-detection")
dataset = project.version(1).download("yolov8")

# Train
from ultralytics import YOLO
model = YOLO("yolov8n.pt")
model.train(
    data=f"{dataset.location}/data.yaml",
    epochs=50,
    imgsz=640,
    batch=16,
    device="0",   # GPU
    name="ambulance_detector"
)
```

5. Download `best.pt` from `runs/train/ambulance_detector/weights/`

---

## STEP 7 — Run Real-Time Detection

```bash
# Webcam
python detect.py

# Specific webcam
python detect.py --source 0

# Image file
python detect.py --source ambulance.jpg

# Video file
python detect.py --source traffic.mp4

# Custom confidence threshold
python detect.py --conf 0.6
```

**Controls while running:**
| Key | Action |
|---|---|
| Q or ESC | Quit |
| S | Save screenshot |
| + | Increase confidence |
| - | Decrease confidence |

---

## STEP 8 — Quick Training Command (Alternative)

You can also train directly from terminal without train.py:

```bash
yolo detect train \
  data=dataset/data.yaml \
  model=yolov8n.pt \
  epochs=50 \
  imgsz=640 \
  batch=16 \
  name=ambulance_detector
```

---

## Model Size Options

| Model | Size | Speed | Accuracy | Best for |
|---|---|---|---|---|
| yolov8n.pt | 6MB | Fastest | Good | Raspberry Pi, mobile |
| yolov8s.pt | 22MB | Fast | Better | Normal PC |
| yolov8m.pt | 50MB | Medium | Great | PC with GPU |
| yolov8l.pt | 87MB | Slow | Excellent | Server/GPU |

Change in `train.py`:
```python
"model": "yolov8s.pt"  # swap here
```

---

## Expected Results After Training

```
mAP50:     0.85+   (good is > 0.80)
Precision: 0.88+
Recall:    0.82+
```

Terminal output during detection:
```
[Frame 45] Detections:
  🚑 ambulance     | conf=0.92 | bbox=[120, 80, 340, 220] | center=[230, 150]
  🚗 car           | conf=0.87 | bbox=[400, 100, 580, 200] | center=[490, 150]
  🚛 truck         | conf=0.79 | bbox=[10, 150, 200, 310]  | center=[105, 230]
```

---

## Connect with Flask Server

Add this to `detect.py` to send detections to your Flask server:

```python
import requests

def send_to_server(detections):
    ambulances = [d for d in detections if d["label"] == "ambulance"]
    if ambulances:
        requests.post("http://localhost:5000/ambulance", json={
            "ambulance_id": "CAM001",
            "lat": 28.6139,
            "lon": 77.2090,
            "status": "active",
            "detections": ambulances
        })
```

Call `send_to_server(detections)` inside the detection loop.

---

## Troubleshooting

| Error | Fix |
|---|---|
| `No module named ultralytics` | `pip install ultralytics` |
| `CUDA out of memory` | Reduce batch size: `"batch": 8` |
| `Cannot open webcam` | Try `--source 1` instead of `0` |
| `No images found` | Check dataset folder structure |
| Low accuracy (mAP < 0.5) | Add more images, train more epochs |
| Model too slow | Use `yolov8n.pt` (nano) instead |