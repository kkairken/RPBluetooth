# AdaFace Quantization Evaluation Report

Generated: 2026-02-09 13:23:28

## Executive Summary

- **Baseline (FP32) Accuracy**: 0.8895
- **Dynamic INT8 Accuracy**: 0.8807 (drop: 0.88%)
- **Static INT8 Accuracy**: 0.8573 (drop: 3.22%)

## Detailed Comparison

| Model | Accuracy | TAR@FAR=1e-3 | TAR@FAR=1e-4 | ROC AUC | Size (MB) | Latency (ms) |
|-------|----------|--------------|--------------|---------|-----------|-------------|
| fp32 | 0.8895 | 0.4593 | 0.3350 | 0.9508 | 166.32 | 34.54 |
| int8_dynamic | 0.8807 | 0.4207 | 0.3893 | 0.9429 | 41.86 | 126.02 |
| int8_static_qdq | 0.8573 | 0.3140 | 0.2583 | 0.9278 | 42.07 | 19.95 |

## Similarity Distributions

| Model | Genuine Mean | Genuine Std | Impostor Mean | Impostor Std | Threshold |
|-------|--------------|-------------|---------------|--------------|----------|
| fp32 | 0.4474 | 0.1610 | 0.1307 | 0.0933 | 0.2577 |
| int8_dynamic | 0.4533 | 0.1597 | 0.1495 | 0.0972 | 0.2954 |
| int8_static_qdq | 0.4405 | 0.1543 | 0.1649 | 0.1013 | 0.2820 |

## Technical Details

### Model
- Architecture: AdaFace (IR-50 backbone)
- Embedding dimension: 512

### Preprocessing
- Input size: 112x112
- Color format: BGR
- Normalization: (pixel/255 - 0.5) / 0.5 -> range [-1, 1]
- Layout: NCHW

### Quantization Settings
- **Dynamic**: QInt8 weights, dynamic activation quantization
- **Static**: QUInt8 activations, QInt8 weights, QDQ format, per-channel
- **Calibration**: MinMax method with ~500 samples

### Evaluation Dataset
- LFW / CFP-FP / AgeDB-30
- 6000 pairs (3000 genuine + 3000 impostor)
- Metric: Cosine similarity on L2-normalized embeddings

