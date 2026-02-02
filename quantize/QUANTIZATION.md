# Обзор квантования (Face Models)

Этот документ содержит краткое описание пайплайна квантования и доступных результатов для моделей в `quantize/`.
GhostFaceNets специально исключён по запросу.

## Краткое описание пайплайна

Общие этапы для всех моделей:
1. Подготовка FP32 ONNX модели (экспорт или скачивание).
2. Базовая оценка на верификационном датасете (LFW или `.bin`).
3. Динамическое INT8 квантование (INT8 веса, динамические активации).
4. Статическое INT8 квантование в формате QDQ (нужна калибровка).
5. Бенчмарк (latency/throughput).
6. Генерация отчёта + JSON результатов.

Ключевые скрипты:
- FaceNet: `quantize/facenet/run_pipeline.py`
- ArcFace (InsightFace pack): `quantize/arcface/run_pipeline.py`
- InsightFace: `quantize/insightface/run_pipeline.py`
- AdaFace: `quantize/adaface/run_pipeline.py`

## Результаты

### FaceNet (LFW, 2026-02-09)
Источник: `quantize/facenet/results/reports/eval_report.md`

| Model | Accuracy | TAR@FAR=1e-3 | TAR@FAR=1e-4 | ROC AUC | Size (MB) | Latency (ms) |
|-------|----------|--------------|--------------|---------|-----------|-------------|
| fp32 | 0.9683 | 0.7857 | 0.7767 | 0.9927 | 89.61 | 7.35 |
| int8_dynamic | 0.9683 | 0.7857 | 0.7760 | 0.9927 | 86.97 | 7.22 |
| int8_static_qdq | 0.9677 | 0.7893 | 0.7780 | 0.9924 | 23.26 | 3.92 |

Примечания:
- Dynamic INT8 не снижает точность.
- Static QDQ даёт ~3.8x сжатие с минимальной потерей точности.

### AdaFace (LFW, 2026-02-09)
Источник: `quantize/adaface/results/reports/eval_report.md`

| Model | Accuracy | TAR@FAR=1e-3 | TAR@FAR=1e-4 | ROC AUC | Size (MB) | Latency (ms) |
|-------|----------|--------------|--------------|---------|-----------|-------------|
| fp32 | 0.8895 | 0.4593 | 0.3350 | 0.9508 | 166.32 | 34.54 |
| int8_dynamic | 0.8807 | 0.4207 | 0.3893 | 0.9429 | 41.86 | 126.02 |
| int8_static_qdq | 0.8573 | 0.3140 | 0.2583 | 0.9278 | 42.07 | 19.95 |

Примечания:
- Dynamic INT8 даёт умеренное падение точности (~0.88% абсолютной).
- Static QDQ заметно снижает точность (~3.22% абсолютной), но ускоряет инференс.

### ArcFace (LFW, 2026-02-09)
Источник: `quantize/arcface/results/results/*.json`

| Model | Accuracy | TAR@FAR=1e-3 | TAR@FAR=1e-4 | ROC AUC | Size (MB) | Latency (ms) |
|-------|----------|--------------|--------------|---------|-----------|-------------|
| fp32 | 0.9400 | 0.7650 | 0.6927 | 0.97987 | 166.31 | 36.86 |
| int8_dynamic | 0.9375 | 0.7510 | 0.7157 | 0.97896 | 41.76 | 125.68 |

Примечания:
- Доступны результаты только для FP32 и Dynamic INT8.
- Static QDQ не запускался для ArcFace в этих результатах.

### InsightFace (ArcFace recognition, GPU run)
Источник: `quantize/insightface/quantization_results_gpu/results/results.json`

| Model | Accuracy | TAR@FAR=1e-3 | TAR@FAR=1e-4 | ROC AUC | Size (MB) | Latency (ms) |
|-------|----------|--------------|--------------|---------|-----------|-------------|
| fp32 | 0.9290 | 0.6240 | 0.6240 | 0.97556 | 166.31 | 42.30 |
| int8_qdq | 0.9190 | 0.6260 | 0.6260 | 0.973384 | 41.78 | 38.23 |

Примечания:
- QDQ INT8 уменьшает размер ~4x при небольшом падении точности (~1.0% абсолютной).

## Препроцессинг по моделям (справочно)

FaceNet:
- Вход: 160x160, RGB, NCHW
- Нормализация: (pixel - 127.5) / 128.0

InsightFace / ArcFace:
- Вход: 112x112, RGB, NCHW
- Нормализация: (pixel - 127.5) / 127.5

AdaFace:
- Вход: 112x112, BGR, NCHW
- Нормализация: (pixel - 127.5) / 127.5

