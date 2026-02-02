#!/usr/bin/env python3
"""
run_pipeline.py - Full quantization pipeline for AdaFace.
"""

import argparse
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict


def setup_directories(output_dir: str) -> Dict[str, Path]:
    base = Path(output_dir)
    dirs = {
        "base": base,
        "models": base / "models",
        "results": base / "results",
        "reports": base / "reports",
        "plots": base / "plots",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def _print_full_results(results: Dict):
    print("\n" + "=" * 70)
    print("FULL RESULTS (JSON)")
    print("=" * 70)
    print(json.dumps(results, indent=2, ensure_ascii=False))


def run_full_pipeline(
    model_path: str = None,
    dataset_path: str = None,
    output_dir: str = "./quantization_results",
    n_calibration: int = 500,
    skip_static: bool = False,
    skip_benchmark: bool = False,
):
    print("=" * 70)
    print("AdaFace Quantization Pipeline")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    from eval_verification import evaluate_model_on_dataset
    from quantize_dynamic import quantize_dynamic, analyze_model_for_quantization
    from quantize_static import (
        quantize_static,
        prepare_calibration_data,
        load_calibration_from_binary,
        load_calibration_from_lfw,
    )
    from benchmark import benchmark_multiple_models, create_comparison_table
    import importlib.util
    _export_spec = importlib.util.spec_from_file_location(
        "adaface_export_to_onnx",
        str(Path(__file__).resolve().parent / "export_to_onnx.py"),
    )
    _export_mod = importlib.util.module_from_spec(_export_spec)
    _export_spec.loader.exec_module(_export_mod)
    export_adaface_to_onnx = _export_mod.export_adaface_to_onnx

    dirs = setup_directories(output_dir)
    all_results = {}

    print("\n" + "=" * 70)
    print("STEP 1: Prepare FP32 Model")
    print("=" * 70)

    if model_path is None:
        print("[INFO] No model provided, exporting AdaFace to ONNX...")
        fp32_model_path = export_adaface_to_onnx(
            model_key="ir50_ms1mv2",
            output_dir=str(dirs["models"]),
        )
    else:
        fp32_model_path = model_path
        print(f"[INFO] Using provided model: {model_path}")

    fp32_output = dirs["models"] / "adaface_fp32.onnx"
    if str(Path(fp32_model_path).resolve()) != str(fp32_output.resolve()):
        shutil.copy(fp32_model_path, fp32_output)
    fp32_model_path = str(fp32_output)

    print(f"[INFO] FP32 model: {fp32_model_path}")
    print("\n[INFO] Analyzing model for quantization...")
    analyze_model_for_quantization(fp32_model_path)

    print("\n" + "=" * 70)
    print("STEP 2: Baseline Evaluation (FP32)")
    print("=" * 70)

    if dataset_path:
        baseline_metrics = evaluate_model_on_dataset(
            model_path=fp32_model_path,
            dataset_path=dataset_path,
            output_dir=str(dirs["results"]),
        )
        all_results["fp32"] = baseline_metrics.to_dict()
    else:
        print("[WARN] No dataset provided, skipping evaluation")
        baseline_metrics = None

    print("\n" + "=" * 70)
    print("STEP 3: Dynamic Quantization")
    print("=" * 70)

    dynamic_model_path = str(dirs["models"] / "adaface_int8_dynamic.onnx")
    quantize_dynamic(
        input_model_path=fp32_model_path,
        output_model_path=dynamic_model_path,
        weight_type="QInt8",
        per_channel=True,
    )

    if dataset_path:
        dynamic_metrics = evaluate_model_on_dataset(
            model_path=dynamic_model_path,
            dataset_path=dataset_path,
            output_dir=str(dirs["results"]),
        )
        all_results["int8_dynamic"] = dynamic_metrics.to_dict()

    if not skip_static:
        print("\n" + "=" * 70)
        print("STEP 4: Static Quantization (QDQ)")
        print("=" * 70)

        static_model_path = str(dirs["models"] / "adaface_int8_static_qdq.onnx")

        if dataset_path:
            print("[INFO] Loading calibration data...")
            if dataset_path.endswith(".bin"):
                raw_images = load_calibration_from_binary(dataset_path, n_calibration)
            else:
                raw_images = load_calibration_from_lfw(dataset_path, n_calibration)

            calibration_data = prepare_calibration_data(
                images=raw_images, n_samples=n_calibration
            )

            quantize_static(
                input_model_path=fp32_model_path,
                output_model_path=static_model_path,
                calibration_data=calibration_data,
                activation_type="QUInt8",
                weight_type="QInt8",
                quant_format="QDQ",
                per_channel=True,
                calibration_method="MinMax",
            )

            static_metrics = evaluate_model_on_dataset(
                model_path=static_model_path,
                dataset_path=dataset_path,
                output_dir=str(dirs["results"]),
            )
            all_results["int8_static_qdq"] = static_metrics.to_dict()
        else:
            print("[WARN] No dataset for calibration, skipping static quantization")

    if not skip_benchmark:
        print("\n" + "=" * 70)
        print("STEP 5: Performance Benchmarking")
        print("=" * 70)

        models_to_benchmark = [fp32_model_path, dynamic_model_path]
        if not skip_static and Path(static_model_path).exists():
            models_to_benchmark.append(static_model_path)

        benchmark_results = benchmark_multiple_models(
            model_paths=models_to_benchmark,
            output_dir=str(dirs["results"]),
            num_threads=4,
            batch_size=32,
        )

        for name, result in benchmark_results.items():
            model_key = name.replace(".onnx", "").replace("adaface_", "")
            if model_key in all_results:
                all_results[model_key]["benchmark"] = result.to_dict()

        print("\n" + create_comparison_table(benchmark_results))

    print("\n" + "=" * 70)
    print("STEP 6: Generate Report")
    print("=" * 70)

    generate_report(all_results, dirs)
    _print_full_results(all_results)

    print("\n" + "=" * 70)
    print("Pipeline completed successfully!")
    print(f"Results saved to: {dirs['base']}")
    print("=" * 70)

    return all_results


def generate_report(results: Dict, dirs: Dict[str, Path]):
    report_path = dirs["reports"] / "eval_report.md"
    with open(report_path, "w") as f:
        f.write("# AdaFace Quantization Evaluation Report\n\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("## Executive Summary\n\n")
        if "fp32" in results and "int8_dynamic" in results:
            fp32_acc = results["fp32"].get("accuracy", 0)
            dyn_acc = results["int8_dynamic"].get("accuracy", 0)
            acc_drop = (fp32_acc - dyn_acc) * 100
            f.write(f"- **Baseline (FP32) Accuracy**: {fp32_acc:.4f}\n")
            f.write(
                f"- **Dynamic INT8 Accuracy**: {dyn_acc:.4f} (drop: {acc_drop:.2f}%)\n"
            )
            if "int8_static_qdq" in results:
                static_acc = results["int8_static_qdq"].get("accuracy", 0)
                static_drop = (fp32_acc - static_acc) * 100
                f.write(
                    f"- **Static INT8 Accuracy**: {static_acc:.4f} (drop: {static_drop:.2f}%)\n"
                )
        f.write("\n")

        f.write("## Detailed Comparison\n\n")
        f.write(
            "| Model | Accuracy | TAR@FAR=1e-3 | TAR@FAR=1e-4 | ROC AUC | Size (MB) | Latency (ms) |\n"
        )
        f.write("|-------|----------|--------------|--------------|---------|-----------|-------------|\n")
        for model_name, metrics in results.items():
            acc = metrics.get("accuracy", 0)
            tar_1e3 = metrics.get("tar_at_far_1e3", 0)
            tar_1e4 = metrics.get("tar_at_far_1e4", 0)
            auc = metrics.get("roc_auc", 0)
            size = metrics.get("model_size_mb", 0)
            latency = metrics.get("inference_latency_ms", 0)
            f.write(
                f"| {model_name} | {acc:.4f} | {tar_1e3:.4f} | {tar_1e4:.4f} | {auc:.4f} | {size:.2f} | {latency:.2f} |\n"
            )
        f.write("\n")

        f.write("## Similarity Distributions\n\n")
        f.write(
            "| Model | Genuine Mean | Genuine Std | Impostor Mean | Impostor Std | Threshold |\n"
        )
        f.write("|-------|--------------|-------------|---------------|--------------|----------|\n")
        for model_name, metrics in results.items():
            g_mean = metrics.get("genuine_mean", 0)
            g_std = metrics.get("genuine_std", 0)
            i_mean = metrics.get("impostor_mean", 0)
            i_std = metrics.get("impostor_std", 0)
            thresh = metrics.get("threshold", 0)
            f.write(
                f"| {model_name} | {g_mean:.4f} | {g_std:.4f} | {i_mean:.4f} | {i_std:.4f} | {thresh:.4f} |\n"
            )
        f.write("\n")

        f.write("## Technical Details\n\n")
        f.write("### Model\n")
        f.write("- Architecture: AdaFace (IR-50 backbone)\n")
        f.write("- Embedding dimension: 512\n\n")

        f.write("### Preprocessing\n")
        f.write("- Input size: 112x112\n")
        f.write("- Color format: BGR\n")
        f.write("- Normalization: (pixel/255 - 0.5) / 0.5 -> range [-1, 1]\n")
        f.write("- Layout: NCHW\n\n")

        f.write("### Quantization Settings\n")
        f.write("- **Dynamic**: QInt8 weights, dynamic activation quantization\n")
        f.write("- **Static**: QUInt8 activations, QInt8 weights, QDQ format, per-channel\n")
        f.write("- **Calibration**: MinMax method with ~500 samples\n\n")

        f.write("### Evaluation Dataset\n")
        f.write("- LFW / CFP-FP / AgeDB-30\n")
        f.write("- 6000 pairs (3000 genuine + 3000 impostor)\n")
        f.write("- Metric: Cosine similarity on L2-normalized embeddings\n\n")

    print(f"[INFO] Report saved to: {report_path}")
    json_path = dirs["reports"] / "full_results.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"[INFO] Full results saved to: {json_path}")


def main():
    parser = argparse.ArgumentParser(description="AdaFace Quantization Pipeline")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--dataset", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default="./quantization_results")
    parser.add_argument("--n-calibration", type=int, default=500)
    parser.add_argument("--skip-static", action="store_true")
    parser.add_argument("--skip-benchmark", action="store_true")

    args = parser.parse_args()
    run_full_pipeline(
        model_path=args.model,
        dataset_path=args.dataset,
        output_dir=args.output_dir,
        n_calibration=args.n_calibration,
        skip_static=args.skip_static,
        skip_benchmark=args.skip_benchmark,
    )


if __name__ == "__main__":
    main()
