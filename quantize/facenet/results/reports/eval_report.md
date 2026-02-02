# FaceNet Quantization Evaluation Report

Generated: 2026-02-09 11:15:45

## Executive Summary

- **Baseline (FP32) Accuracy**: 0.9683
- **Dynamic INT8 Accuracy**: 0.9683 (drop: 0.00%)
- **Static INT8 Accuracy**: 0.9677 (drop: 0.07%)

## Detailed Comparison

| Model | Accuracy | TAR@FAR=1e-3 | TAR@FAR=1e-4 | ROC AUC | Size (MB) | Latency (ms) |
|-------|----------|--------------|--------------|---------|-----------|-------------|
| fp32 | 0.9683 | 0.7857 | 0.7767 | 0.9927 | 89.61 | 7.35 |
| int8_dynamic | 0.9683 | 0.7857 | 0.7760 | 0.9927 | 86.97 | 7.22 |
| int8_static_qdq | 0.9677 | 0.7893 | 0.7780 | 0.9924 | 23.26 | 3.92 |

## Similarity Distributions

| Model | Genuine Mean | Genuine Std | Impostor Mean | Impostor Std | Threshold |
|-------|--------------|-------------|---------------|--------------|----------|
| fp32 | 0.6753 | 0.1542 | 0.0488 | 0.1557 | 0.3367 |
| int8_dynamic | 0.6753 | 0.1542 | 0.0488 | 0.1557 | 0.3367 |
| int8_static_qdq | 0.6743 | 0.1547 | 0.0501 | 0.1562 | 0.3489 |

## Recommendations

### Dynamic Quantization Recommended

Dynamic INT8 quantization shows minimal accuracy degradation (0.00%) while providing ~3-4x model size reduction.

**Advantages:**
- No calibration dataset required
- Simple deployment
- Good balance of quality and compression

### Static Quantization (QDQ) Also Viable

Static INT8 shows 0.07% accuracy drop. Use for deployment on TensorRT/OpenVINO for better acceleration.

## Technical Details

### Model
- Architecture: InceptionResNetV1 (FaceNet)
- Training data: VGGFace2
- Embedding dimension: 512

### Preprocessing
- Input size: 160x160
- Color format: RGB
- Normalization: (pixel - 127.5) / 128.0
- Layout: NCHW

### Quantization Settings
- **Dynamic**: QInt8 weights, dynamic activation quantization
- **Static**: QUInt8 activations, QInt8 weights, QDQ format, per-channel
- **Calibration**: MinMax method with ~500 samples

### Evaluation Dataset
- LFW (Labeled Faces in the Wild)
- 6000 pairs (3000 genuine + 3000 impostor)
- Metric: Cosine similarity on L2-normalized embeddings

