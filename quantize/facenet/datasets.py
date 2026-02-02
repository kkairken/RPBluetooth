#!/usr/bin/env python3
"""
datasets.py - Переиспользование загрузчиков датасетов из insightface

Все классы загружаются из insightface/datasets.py:
- LFWDataset
- BinaryDataset
- VerificationPair
- CFPDataset
- AgeDBDataset
"""

import sys
from pathlib import Path

# Добавляем insightface в sys.path для импорта
insightface_dir = Path(__file__).parent.parent / "insightface"
sys.path.insert(0, str(insightface_dir))

from datasets import (
    LFWDataset,
    BinaryDataset,
    VerificationPair,
    CFPDataset,
    AgeDBDataset,
    download_lfw,
)
