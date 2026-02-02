#!/usr/bin/env python3
"""
Thin wrapper around InsightFace dynamic quantization utilities.
"""

import sys
from pathlib import Path

INSIGHTFACE_DIR = Path(__file__).resolve().parent.parent / "insightface"
sys.path.insert(0, str(INSIGHTFACE_DIR))

from quantize_dynamic import (  # noqa: F401
    quantize_dynamic,
    validate_quantized_model,
    analyze_model_for_quantization,
)
