#!/usr/bin/env python3
"""
export_to_onnx.py - Download GhostFaceNets weights and export to ONNX.

Default model: GhostFaceNet_W1.3_S1_ArcFace (official release).
"""

import argparse
import os
import sys
import time
import zipfile
from pathlib import Path
from typing import Optional
from urllib.request import urlretrieve


def _download_with_progress(url: str, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from tqdm import tqdm
    except Exception:
        tqdm = None

    if tqdm is None:
        print(f"[INFO] Downloading: {url}")
        urlretrieve(url, output_path)
        return

    pbar = tqdm(unit="B", unit_scale=True, unit_divisor=1024, desc=output_path.name)

    def _hook(block_num, block_size, total_size):
        if total_size > 0:
            if pbar.total != total_size:
                pbar.total = total_size
        pbar.update(block_size)

    urlretrieve(url, output_path, reporthook=_hook)
    pbar.close()


GHOSTFACENETS_MODELS = {
    "w1.3_s1_arcface_v1.2": {
        "filename": "GhostFaceNet_W1.3_S1_ArcFace.h5",
        "url": "https://github.com/HamadYA/GhostFaceNets/releases/download/v1.2/GhostFaceNet_W1.3_S1_ArcFace.h5",
    },
}

GHOSTFACENETS_REPO_ZIP = "https://github.com/HamadYA/GhostFaceNets/archive/refs/heads/main.zip"


def _download_repo(cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    repo_dir = cache_dir / "GhostFaceNets-main"
    if repo_dir.exists():
        return repo_dir

    zip_path = cache_dir / "GhostFaceNets-main.zip"
    print(f"[INFO] Downloading GhostFaceNets repo: {GHOSTFACENETS_REPO_ZIP}")
    _download_with_progress(GHOSTFACENETS_REPO_ZIP, zip_path)

    print(f"[INFO] Extracting repo to: {cache_dir}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(cache_dir)

    zip_path.unlink(missing_ok=True)
    return repo_dir


def download_weights(model_key: str, output_dir: str) -> str:
    if model_key not in GHOSTFACENETS_MODELS:
        raise ValueError(f"Unknown model: {model_key}. Available: {list(GHOSTFACENETS_MODELS)}")

    info = GHOSTFACENETS_MODELS[model_key]
    output_path = Path(output_dir) / info["filename"]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists():
        print(f"[INFO] Weights already exist: {output_path}")
        return str(output_path)

    print(f"[INFO] Downloading weights: {info['url']}")
    _download_with_progress(info["url"], output_path)
    return str(output_path)


def export_ghostfacenets_to_onnx(
    model_key: str = "w1.3_s1_arcface_v1.2",
    output_dir: str = "./models",
    onnx_opset: int = 13,
    input_size: int = 112,
    cache_dir: Optional[str] = None,
):
    # Stabilize TF import on some environments (Mac/CPU)
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")
    os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "1")
    os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")

    print("[INFO] Importing TensorFlow...", flush=True)
    t0 = time.perf_counter()
    try:
        import tensorflow as tf
    except ImportError:
        print("Install dependencies: pip install tensorflow")
        sys.exit(1)
    print(f"[INFO] TensorFlow imported in {time.perf_counter() - t0:.2f}s", flush=True)

    weights_path = download_weights(model_key, output_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    cache_root = Path(cache_dir) if cache_dir else Path.home() / ".cache" / "ghostfacenets_repo"
    repo_dir = _download_repo(cache_root)
    sys.path.insert(0, str(repo_dir))

    print("[INFO] Importing GhostFaceNets module...", flush=True)
    t1 = time.perf_counter()
    try:
        import GhostFaceNets
        import inspect
    except Exception as e:
        print(f"[ERROR] Failed to import GhostFaceNets: {e}")
        print("[HINT] Install deps: pip install keras_cv_attention_models")
        sys.exit(1)
    print(f"[INFO] GhostFaceNets imported in {time.perf_counter() - t1:.2f}s", flush=True)

    print("[INFO] Building GhostFaceNets backbone...", flush=True)
    t2 = time.perf_counter()
    sig = inspect.signature(GhostFaceNets.buildin_models)
    kwargs = {}
    if "stem_model" in sig.parameters:
        kwargs["stem_model"] = "ghostnetv1"
    if "dropout" in sig.parameters:
        kwargs["dropout"] = 0
    if "emb_shape" in sig.parameters:
        kwargs["emb_shape"] = 512
    if "output_layer" in sig.parameters:
        kwargs["output_layer"] = "GDC"
    if "bn_momentum" in sig.parameters:
        kwargs["bn_momentum"] = 0.9
    if "bn_epsilon" in sig.parameters:
        kwargs["bn_epsilon"] = 1e-5
    if "width_multiplier" in sig.parameters:
        kwargs["width_multiplier"] = 1.3
    if "strides" in sig.parameters:
        kwargs["strides"] = 1

    model = GhostFaceNets.buildin_models(**kwargs)
    print(f"[INFO] Model built in {time.perf_counter() - t2:.2f}s", flush=True)

    print(f"[INFO] Loading weights: {weights_path}", flush=True)
    t3 = time.perf_counter()
    try:
        model.load_weights(weights_path)
    except Exception:
        model.load_weights(weights_path, by_name=True, skip_mismatch=True)
    print(f"[INFO] Weights loaded in {time.perf_counter() - t3:.2f}s", flush=True)

    onnx_path = output_path / "ghostfacenets_fp32.onnx"

    print(f"[INFO] Exporting to ONNX: {onnx_path}", flush=True)
    t4 = time.perf_counter()
    try:
        import tf2onnx

        spec = (tf.TensorSpec((None, input_size, input_size, 3), tf.float32, name="input"),)
        _ = tf2onnx.convert.from_keras(model, input_signature=spec, opset=onnx_opset, output_path=str(onnx_path))
    except Exception as e:
        print(f"[ERROR] ONNX export failed: {e}")
        print("Install tf2onnx: pip install tf2onnx")
        sys.exit(1)
    print(f"[INFO] ONNX export done in {time.perf_counter() - t4:.2f}s", flush=True)

    print(f"[OK] Exported: {onnx_path}")
    return str(onnx_path)


def main():
    parser = argparse.ArgumentParser(description="Export GhostFaceNets to ONNX")
    parser.add_argument("--model", type=str, default="w1.3_s1_arcface_v1.2",
                        choices=list(GHOSTFACENETS_MODELS.keys()))
    parser.add_argument("--output-dir", type=str, default="./models")
    parser.add_argument("--opset", type=int, default=13)
    parser.add_argument("--input-size", type=int, default=112)

    args = parser.parse_args()
    export_ghostfacenets_to_onnx(
        model_key=args.model,
        output_dir=args.output_dir,
        onnx_opset=args.opset,
        input_size=args.input_size,
    )


if __name__ == "__main__":
    main()
