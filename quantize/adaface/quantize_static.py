#!/usr/bin/env python3
"""
AdaFace static quantization utilities.
Uses InsightFace quantization core but with AdaFace preprocessing defaults.
"""

import sys
import numpy as np
from pathlib import Path
from typing import List
from tqdm import tqdm
import cv2

INSIGHTFACE_DIR = Path(__file__).resolve().parent.parent / "insightface"
sys.path.insert(0, str(INSIGHTFACE_DIR))

from quantize_static import (  # noqa: F401
    quantize_static as _quantize_static,
    validate_quantized_model,
    load_calibration_from_lfw,
    load_calibration_from_binary,
)


def prepare_calibration_data(
    images: List[np.ndarray],
    n_samples: int = 500,
    input_size: tuple = (112, 112),
    input_mean: float = 127.5,
    input_std: float = 127.5,
) -> List[np.ndarray]:
    print(f"[INFO] Preparing {min(n_samples, len(images))} calibration samples...")

    indices = np.random.permutation(len(images))[:n_samples]
    calibration_data = []

    for idx in tqdm(indices, desc="Preprocessing"):
        img = images[idx]
        if img.shape[:2] != (input_size[1], input_size[0]):
            img = cv2.resize(img, input_size, interpolation=cv2.INTER_LINEAR)

        # AdaFace expects BGR input
        img = img.astype(np.float32)
        img = (img - input_mean) / input_std
        img = img.transpose(2, 0, 1)
        img = np.expand_dims(img, axis=0)

        calibration_data.append(img)

    return calibration_data


def quantize_static(
    input_model_path: str,
    output_model_path: str,
    calibration_data: List[np.ndarray],
    input_name: str = None,
    activation_type: str = "QUInt8",
    weight_type: str = "QInt8",
    quant_format: str = "QDQ",
    per_channel: bool = True,
    reduce_range: bool = False,
    calibration_method: str = "MinMax",
    extra_options: dict = None,
) -> str:
    return _quantize_static(
        input_model_path=input_model_path,
        output_model_path=output_model_path,
        calibration_data=calibration_data,
        input_name=input_name,
        activation_type=activation_type,
        weight_type=weight_type,
        quant_format=quant_format,
        per_channel=per_channel,
        reduce_range=reduce_range,
        calibration_method=calibration_method,
        extra_options=extra_options,
    )
