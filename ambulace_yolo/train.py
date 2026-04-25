"""
train.py — YOLOv8 Ambulance Detection Training Script
======================================================
Run: python train.py
"""

from ultralytics import YOLO
import yaml
import os
import torch

# ── CONFIGURATION ─────────────────────────────────────────────────────────────

CONFIG = {
    "model": "yolov8n.pt",                 # change to yolov8s.pt for better accuracy
    "data": "dataset/data.yaml",           # ✅ FIXED PATH
    "epochs": 50,
    "imgsz": 640,
    "batch": 16,
    "patience": 10,
    "device": 0 if torch.cuda.is_available() else "cpu",  # ✅ AUTO DEVICE
    "project": "runs/train",
    "name": "ambulance_detector",
    "exist_ok": True,
}

# ── CREATE DATASET YAML (SAFE MODE) ───────────────────────────────────────────

def create_dataset_yaml():
    """Create data.yaml only if not present."""
    yaml_path = "dataset/data.yaml"

    if not os.path.exists(yaml_path):
        os.makedirs("dataset/images/train", exist_ok=True)
        os.makedirs("dataset/images/val", exist_ok=True)
        os.makedirs("dataset/labels/train", exist_ok=True)
        os.makedirs("dataset/labels/val", exist_ok=True)

        yaml_content = {
            "path": os.path.abspath("dataset"),
            "train": "images/train",
            "val": "images/val",
            "nc": 1,
            "names": ["ambulance"],
        }

        with open(yaml_path, "w") as f:
            yaml.dump(yaml_content, f)

        print(f"✓ Created {yaml_path}")
    else:
        print(f"✓ Using existing {yaml_path}")

    return yaml_path

# ── CHECK DATASET ─────────────────────────────────────────────────────────────

def check_dataset():
    train_path = "dataset/images/train"

    if not os.path.exists(train_path):
        print("\n❌ dataset/images/train not found!")
        return False

    train_imgs = [
        f for f in os.listdir(train_path)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ]

    if len(train_imgs) == 0:
        print("\n⚠️ No training images found!")
        print("→ Add images to dataset/images/train/")
        print("→ Add labels to dataset/labels/train/")
        return False

    print(f"\n✅ Found {len(train_imgs)} training images")
    return True

# ── TRAIN FUNCTION ────────────────────────────────────────────────────────────

def train():
    print("=" * 60)
    print("🚑 YOLOv8 Ambulance Detector Training Started")
    print("=" * 60)

    create_dataset_yaml()

    if not check_dataset():
        return

    # Load model
    print(f"\n→ Loading model: {CONFIG['model']}")
    model = YOLO(CONFIG["model"])

    print(f"→ Training on device: {CONFIG['device']}")
    print(f"→ Epochs: {CONFIG['epochs']}\n")

    # Train
    results = model.train(
        data=CONFIG["data"],
        epochs=CONFIG["epochs"],
        imgsz=CONFIG["imgsz"],
        batch=CONFIG["batch"],
        patience=CONFIG["patience"],
        device=CONFIG["device"],
        project=CONFIG["project"],
        name=CONFIG["name"],
        exist_ok=CONFIG["exist_ok"],
        augment=True,        # ✅ improves accuracy
        plots=True,
        save=True,
        verbose=True,
    )

    # Save path
    best_model_path = f"{CONFIG['project']}/{CONFIG['name']}/weights/best.pt"

    print("\n" + "=" * 60)
    print("🎉 TRAINING COMPLETE!")
    print(f"📁 Best Model: {best_model_path}")
    print("=" * 60)

    # Validation
    print("\n→ Running validation...")
    metrics = model.val()

    print(f"\n📊 RESULTS:")
    print(f"mAP50    : {metrics.box.map50:.3f}")
    print(f"mAP50-95 : {metrics.box.map:.3f}")
    print(f"Precision: {metrics.box.mp:.3f}")
    print(f"Recall   : {metrics.box.mr:.3f}")

    # Save log
    with open("training_log.txt", "w") as f:
        f.write(str(metrics))

    # Test prediction
    print("\n→ Testing model on validation images...")
    model.predict(source="dataset/images/val", show=True)

    return results


# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    train()