#!/usr/bin/env python3
"""
Thin wrapper around InsightFace benchmark utilities.
"""

import sys
from pathlib import Path

INSIGHTFACE_DIR = Path(__file__).resolve().parent.parent / "insightface"
sys.path.insert(0, str(INSIGHTFACE_DIR))

from benchmark import (  # noqa: F401
    BenchmarkResult,
    ONNXBenchmark,
    benchmark_multiple_models,
    create_comparison_table,
)
