#!/usr/bin/env python3
"""
Local registration tool (without BLE).
Use this when BLE is not available.

Usage:
    python tools/local_register.py \
        --employee-id EMP001 \
        --display-name "Your Name" \
        --photos photo1.jpg photo2.jpg \
        --access-start 2025-01-01 \
        --access-end 2026-12-31
"""
import argparse
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import cv2
from datetime import datetime
from db import Database
from face.detector import FaceDetector
from face.align import FaceAligner

# Try ONNX Runtime first, fallback to OpenCV DNN
try:
    from face.embedder_onnx import FaceEmbedder
except ImportError:
    from face.embedder_opencv import FaceEmbedderOpenCV as FaceEmbedder


def main():
    parser = argparse.ArgumentParser(description='Local employee registration')
    parser.add_argument('--employee-id', required=True, help='Employee ID')
    parser.add_argument('--display-name', required=True, help='Display name')
    parser.add_argument('--photos', nargs='+', required=True, help='Photo files')
    parser.add_argument('--access-start', default='2025-01-01', help='Access start date (YYYY-MM-DD)')
    parser.add_argument('--access-end', default='2026-12-31', help='Access end date (YYYY-MM-DD)')
    parser.add_argument('--db-path', default='data/access_control.db', help='Database path')
    parser.add_argument('--model-path', default='models/insightface_medium.onnx', help='Model path')

    args = parser.parse_args()

    print(f"Registering employee: {args.employee_id} ({args.display_name})")

    # Initialize components
    print("Loading models...")
    db = Database(args.db_path)
    detector = FaceDetector()
    aligner = FaceAligner()
    embedder = FaceEmbedder(args.model_path)

    # Process photos
    embeddings = []
    for photo_path in args.photos:
        print(f"  Processing: {photo_path}")

        if not os.path.exists(photo_path):
            print(f"    ERROR: File not found")
            continue

        img = cv2.imread(photo_path)
        if img is None:
            print(f"    ERROR: Cannot read image")
            continue

        faces = detector.detect(img)
        if not faces:
            print(f"    ERROR: No face detected")
            continue

        # Use largest face
        largest = max(faces, key=lambda f: f[2] * f[3])
        aligned = aligner.align(img, largest)

        if aligned is None:
            print(f"    ERROR: Alignment failed")
            continue

        embedding = embedder.compute_embedding(aligned)
        if embedding is None:
            print(f"    ERROR: Embedding failed")
            continue

        embeddings.append(embedding)
        print(f"    OK: Face detected and processed")

    if not embeddings:
        print("ERROR: No valid embeddings extracted")
        sys.exit(1)

    # Parse dates
    access_start = datetime.strptime(args.access_start, '%Y-%m-%d')
    access_end = datetime.strptime(args.access_end, '%Y-%m-%d')

    # Register employee
    db.upsert_employee(
        employee_id=args.employee_id,
        display_name=args.display_name,
        access_start=access_start,
        access_end=access_end,
        is_active=True
    )

    # Delete old embeddings and add new ones
    db.delete_embeddings(args.employee_id)
    for emb in embeddings:
        db.add_embedding(args.employee_id, emb)

    print(f"\n✅ Registered {args.employee_id} with {len(embeddings)} embedding(s)")
    print(f"   Access period: {args.access_start} to {args.access_end}")


if __name__ == '__main__':
    main()
