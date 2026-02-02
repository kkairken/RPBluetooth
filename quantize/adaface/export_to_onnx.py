#!/usr/bin/env python3
"""
export_to_onnx.py - Download AdaFace checkpoint and export to ONNX.

Default model: AdaFace IR-50 trained on MS1MV2.
"""

import argparse
import os
import sys
import shutil
import zipfile
from pathlib import Path
from typing import Optional
from urllib.request import urlretrieve


ADAFACE_MODELS = {
    "ir50_ms1mv2": {
        "filename": "adaface_ir50_ms1mv2.ckpt",
        "gdrive_id": "1eUaSHG4pGlIZK7hBkqjyp2fc2epKoBvI",
    },
}

ADAFACE_REPO_ZIP = "https://github.com/mk-minchul/AdaFace/archive/refs/heads/master.zip"


def _download_gdrive(file_id: str, output_path: Path):
    try:
        import gdown
    except ImportError:
        print("Install gdown: pip install gdown")
        sys.exit(1)

    url = f"https://drive.google.com/uc?id={file_id}"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] Downloading checkpoint from Google Drive to: {output_path}")
    gdown.download(url, str(output_path), quiet=False)


def _download_adaface_repo(cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    repo_dir = cache_dir / "AdaFace-master"
    if repo_dir.exists():
        return repo_dir

    zip_path = cache_dir / "AdaFace-master.zip"
    print(f"[INFO] Downloading AdaFace repo: {ADAFACE_REPO_ZIP}")
    urlretrieve(ADAFACE_REPO_ZIP, zip_path)

    print(f"[INFO] Extracting repo to: {cache_dir}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(cache_dir)

    zip_path.unlink(missing_ok=True)
    return repo_dir


def download_adaface_checkpoint(
    model_key: str = "ir50_ms1mv2",
    output_dir: str = "./models",
) -> str:
    if model_key not in ADAFACE_MODELS:
        raise ValueError(f"Unknown model: {model_key}. Available: {list(ADAFACE_MODELS)}")

    info = ADAFACE_MODELS[model_key]
    output_path = Path(output_dir) / info["filename"]
    if output_path.exists():
        print(f"[INFO] Checkpoint already exists: {output_path}")
        return str(output_path)

    _download_gdrive(info["gdrive_id"], output_path)
    return str(output_path)


def export_adaface_to_onnx(
    model_key: str = "ir50_ms1mv2",
    output_dir: str = "./models",
    cache_dir: Optional[str] = None,
) -> str:
    try:
        import torch
        import onnx
    except ImportError:
        print("Install dependencies: pip install torch onnx")
        sys.exit(1)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    ckpt_path = Path(download_adaface_checkpoint(model_key, output_dir))

    cache_root = Path(cache_dir) if cache_dir else Path.home() / ".cache" / "adaface_repo"
    repo_dir = _download_adaface_repo(cache_root)

    # Place checkpoint where AdaFace expects it by default
    pretrained_dir = repo_dir / "pretrained"
    pretrained_dir.mkdir(parents=True, exist_ok=True)
    dst_ckpt = pretrained_dir / ckpt_path.name
    if str(ckpt_path.resolve()) != str(dst_ckpt.resolve()):
        shutil.copy(ckpt_path, dst_ckpt)

    sys.path.insert(0, str(repo_dir))
    try:
        import net
    except Exception as e:
        print(f"[ERROR] Failed to import AdaFace net: {e}")
        sys.exit(1)

    print("[INFO] Loading AdaFace model (IR-50) on CPU...")
    model = net.build_model("ir_50")
    ckpt = torch.load(str(ckpt_path), map_location="cpu")
    state = ckpt["state_dict"] if isinstance(ckpt, dict) and "state_dict" in ckpt else ckpt
    model_statedict = {
        key[6:]: val for key, val in state.items() if key.startswith("model.")
    }
    model.load_state_dict(model_statedict, strict=True)
    model.eval()

    class _AdaFaceWrapper(torch.nn.Module):
        def __init__(self, backbone):
            super().__init__()
            self.backbone = backbone

        def forward(self, x):
            out = self.backbone(x)
            if isinstance(out, (tuple, list)):
                return out[0]
            return out

    wrapper = _AdaFaceWrapper(model)

    dummy_input = torch.randn(1, 3, 112, 112)
    onnx_path = output_path / "adaface_fp32.onnx"

    print(f"[INFO] Exporting to ONNX: {onnx_path}")
    torch.onnx.export(
        wrapper,
        dummy_input,
        str(onnx_path),
        input_names=["input"],
        output_names=["embedding"],
        dynamic_axes={"input": {0: "batch_size"}, "embedding": {0: "batch_size"}},
        opset_version=14,
        do_constant_folding=True,
    )

    print("[INFO] Validating ONNX model...")
    model_onnx = onnx.load(str(onnx_path))
    onnx.checker.check_model(model_onnx)

    print(f"[OK] Exported: {onnx_path}")
    return str(onnx_path)


def main():
    parser = argparse.ArgumentParser(description="Export AdaFace to ONNX")
    parser.add_argument(
        "--model",
        type=str,
        default="ir50_ms1mv2",
        choices=list(ADAFACE_MODELS.keys()),
        help="AdaFace model key",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./models",
        help="Directory for ONNX output",
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=None,
        help="Cache dir for AdaFace repo",
    )

    args = parser.parse_args()
    export_adaface_to_onnx(args.model, args.output_dir, args.cache_dir)


if __name__ == "__main__":
    main()
