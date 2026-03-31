from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

OVERSIZED_PREFLIGHT_EXIT_CODE = 12


class OversizedPreflightError(RuntimeError):
    pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run nnU-Net prediction through a Windows-safe SpineLab sidecar path "
            "that performs segmentation export in-process."
        )
    )
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--preprocessed-root", type=Path, required=True)
    parser.add_argument("--fold", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--device", choices=("cuda", "cpu"), required=True)
    parser.add_argument("--npp", type=int, default=2)
    parser.add_argument(
        "--nps",
        type=int,
        default=2,
        help=(
            "Accepted for compatibility with the shared driver. The Windows sidecar "
            "exports predictions in-process, so this value is informational only."
        ),
    )
    parser.add_argument("--disable_tta", action="store_true")
    parser.add_argument("--continue_prediction", action="store_true")
    parser.add_argument("--fail_on_oversized_preflight", action="store_true")
    return parser.parse_args(argv)


def _configure_environment(args: argparse.Namespace) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.raw_root.mkdir(parents=True, exist_ok=True)
    args.preprocessed_root.mkdir(parents=True, exist_ok=True)
    args.results_root.mkdir(parents=True, exist_ok=True)
    os.environ["nnUNet_results"] = str(args.results_root)
    os.environ["nnUNet_raw"] = str(args.raw_root)
    os.environ["nnUNet_preprocessed"] = str(args.preprocessed_root)


def _case_output_stem(path: Path) -> str:
    name = path.name
    for suffix in (".nii.gz", ".nii"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def _coerce_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _coerce_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_coerce_json_value(item) for item in value]
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return _coerce_json_value(tolist())
    return str(value)


def _product(values: Sequence[int]) -> int:
    result = 1
    for value in values:
        result *= int(value)
    return result


def _compute_sliding_window_steps(
    image_size: Sequence[int],
    tile_size: Sequence[int],
    tile_step_size: float,
) -> list[list[int]]:
    if len(image_size) != len(tile_size):
        raise ValueError("image_size and tile_size must have the same rank.")
    if not 0 < tile_step_size <= 1:
        raise ValueError("tile_step_size must be larger than 0 and smaller than or equal to 1.")
    if any(
        int(image_dim) < int(tile_dim)
        for image_dim, tile_dim in zip(image_size, tile_size, strict=True)
    ):
        raise ValueError("image_size must be as large or larger than tile_size.")

    steps: list[list[int]] = []
    for image_dim, tile_dim in zip(image_size, tile_size, strict=True):
        target_step = int(tile_dim) * float(tile_step_size)
        num_steps = math.ceil((int(image_dim) - int(tile_dim)) / target_step) + 1
        max_step_value = int(image_dim) - int(tile_dim)
        if num_steps > 1:
            actual_step_size = max_step_value / (num_steps - 1)
            steps.append([int(round(actual_step_size * index)) for index in range(num_steps)])
        else:
            steps.append([0])
    return steps


def _summarize_data_properties(properties: dict[str, object]) -> dict[str, object]:
    selected_keys = (
        "shape_before_cropping",
        "shape_after_cropping_and_before_resampling",
        "bbox_used_for_cropping",
        "spacing",
        "spacing_transposed",
        "shape_after_resampling",
        "original_size_of_raw_data",
        "original_spacing",
    )
    return {
        "available_keys": sorted(str(key) for key in properties),
        "selected": {
            key: _coerce_json_value(properties[key])
            for key in selected_keys
            if key in properties
        },
    }


def _build_case_diagnostics(
    *,
    case_id: str,
    args: argparse.Namespace,
    input_shape_cxyz: Sequence[int],
    patch_size: Sequence[int],
    tile_step_size: float,
    segmentation_heads: int,
    use_mirroring: bool,
    mirroring_axes: Sequence[int] | None,
    perform_everything_on_device: bool,
    output_file: Path,
    properties: dict[str, object],
    device_name: str | None = None,
    device_total_memory_bytes: int | None = None,
) -> dict[str, object]:
    input_shape = [int(value) for value in input_shape_cxyz]
    input_spatial_shape = input_shape[1:]
    patch = [int(value) for value in patch_size]
    padded_spatial_shape = [
        max(int(image_dim), int(tile_dim))
        for image_dim, tile_dim in zip(input_spatial_shape, patch, strict=True)
    ]
    sliding_window_steps = _compute_sliding_window_steps(
        padded_spatial_shape,
        patch,
        tile_step_size,
    )
    sliding_window_axis_counts = [len(axis_steps) for axis_steps in sliding_window_steps]
    sliding_window_count = _product(sliding_window_axis_counts)
    padded_voxel_count = _product(padded_spatial_shape)
    logits_bytes = int(segmentation_heads) * padded_voxel_count * 2
    accumulation_bytes = padded_voxel_count * 2
    results_arrays_total_bytes = logits_bytes + accumulation_bytes
    mirroring_axes_tuple = tuple(int(value) for value in mirroring_axes or ())
    mirror_variant_count = 1 if not use_mirroring else 2 ** len(mirroring_axes_tuple)
    diagnostics: dict[str, object] = {
        "case_id": case_id,
        "fold": str(args.fold),
        "checkpoint_name": str(args.checkpoint),
        "device": {
            "requested_device": str(args.device),
            "device_name": device_name or "",
            "total_memory_bytes": int(device_total_memory_bytes or 0),
        },
        "model": {
            "model_dir": str(args.model_dir),
            "results_root": str(args.results_root),
            "raw_root": str(args.raw_root),
            "preprocessed_root": str(args.preprocessed_root),
        },
        "inference": {
            "perform_everything_on_device_requested": bool(perform_everything_on_device),
            "use_mirroring": bool(use_mirroring),
            "mirroring_axes": list(mirroring_axes_tuple),
            "mirror_variant_count": mirror_variant_count,
            "tile_step_size": float(tile_step_size),
            "patch_size": patch,
            "segmentation_heads": int(segmentation_heads),
            "preprocessing_workers": int(args.npp),
            "export_workers_arg": int(args.nps),
        },
        "input_tensor": {
            "shape_cxyz": input_shape,
            "spatial_shape": input_spatial_shape,
            "padded_spatial_shape": padded_spatial_shape,
            "padded_voxel_count": padded_voxel_count,
        },
        "sliding_window": {
            "axis_steps": sliding_window_steps,
            "axis_step_counts": sliding_window_axis_counts,
            "count": sliding_window_count,
        },
        "estimates": {
            "results_logits_bytes_fp16": logits_bytes,
            "results_accumulator_bytes_fp16": accumulation_bytes,
            "results_arrays_total_bytes_fp16": results_arrays_total_bytes,
        },
        "data_properties": _summarize_data_properties(properties),
        "diagnostics_path": str(output_file),
    }
    warnings: list[str] = []
    if device_total_memory_bytes:
        diagnostics["estimates"]["results_arrays_fraction_of_total_device_memory"] = (
            results_arrays_total_bytes / device_total_memory_bytes
        )
        exceeds_total = results_arrays_total_bytes > device_total_memory_bytes
        diagnostics["estimates"]["results_arrays_exceed_total_device_memory"] = exceeds_total
        if exceeds_total:
            warnings.append(
                "Estimated fp16 results arrays exceed total device memory; on-device "
                "accumulation is unlikely to fit."
            )
        elif results_arrays_total_bytes > int(device_total_memory_bytes * 0.75):
            warnings.append(
                "Estimated fp16 results arrays exceed 75% of total device memory; "
                "fallback or poor throughput is possible."
            )
    if sliding_window_count >= 256:
        warnings.append(
            "Sliding-window count is high enough to expect a long-running fullres pass."
        )
    diagnostics["warnings"] = warnings
    return diagnostics


def _emit_case_diagnostics(diagnostics: dict[str, object]) -> None:
    device = diagnostics.get("device", {})
    input_tensor = diagnostics.get("input_tensor", {})
    sliding_window = diagnostics.get("sliding_window", {})
    estimates = diagnostics.get("estimates", {})
    print("SpineLab nnU-Net preflight:")
    print(f"  case: {diagnostics['case_id']}")
    print(f"  fold: {diagnostics['fold']}")
    print(f"  checkpoint: {diagnostics['checkpoint_name']}")
    print(f"  device: {device.get('requested_device')} {device.get('device_name')}".rstrip())
    print(f"  input shape (cxyz): {input_tensor.get('shape_cxyz')}")
    print(f"  padded spatial shape: {input_tensor.get('padded_spatial_shape')}")
    print(f"  patch size: {diagnostics['inference']['patch_size']}")
    print(f"  tile step size: {diagnostics['inference']['tile_step_size']}")
    print(
        f"  sliding windows: {sliding_window.get('count')} "
        f"(axis counts {sliding_window.get('axis_step_counts')})"
    )
    print(
        "  estimated fp16 results arrays: "
        f"{estimates.get('results_arrays_total_bytes_fp16')} bytes"
    )
    fraction = estimates.get("results_arrays_fraction_of_total_device_memory")
    if fraction is not None:
        print(f"  results arrays fraction of total device memory: {fraction:.3f}")
    for warning in diagnostics.get("warnings", []):
        print(f"  warning: {warning}")
    print(f"  diagnostics path: {diagnostics['diagnostics_path']}")


def _oversized_preflight_reason(diagnostics: dict[str, object]) -> str | None:
    estimates = diagnostics.get("estimates", {})
    if not isinstance(estimates, dict):
        return None
    if not bool(estimates.get("results_arrays_exceed_total_device_memory")):
        return None
    total_bytes = estimates.get("results_arrays_total_bytes_fp16")
    total_memory_bytes = (
        diagnostics.get("device", {}).get("total_memory_bytes")
        if isinstance(diagnostics.get("device"), dict)
        else None
    )
    return (
        "SpineLab nnU-Net guard blocked this case because the estimated fp16 "
        f"results arrays ({total_bytes} bytes) exceed total device memory "
        f"({total_memory_bytes} bytes)."
    )


def _write_prediction_metadata(predictor, args: argparse.Namespace) -> None:
    payload = {
        "folder_with_segs_from_prev_stage": None,
        "list_of_lists_or_source_folder": str(args.input_dir),
        "num_parts": 1,
        "num_processes_preprocessing": args.npp,
        "num_processes_segmentation_export": 0,
        "output_folder_or_list_of_truncated_output_files": str(args.output_dir),
        "overwrite": not args.continue_prediction,
        "part_id": 0,
        "save_probabilities": False,
        "checkpoint_name": args.checkpoint,
        "disable_tta": args.disable_tta,
        "device": args.device,
        "sidecar_mode": "windows-inprocess-export",
    }
    (args.output_dir / "predict_from_raw_data_args.json").write_text(
        json.dumps(payload, indent=4),
        encoding="utf-8",
    )
    (args.output_dir / "dataset.json").write_text(
        json.dumps(predictor.dataset_json, indent=2),
        encoding="utf-8",
    )
    (args.output_dir / "plans.json").write_text(
        json.dumps(predictor.plans_manager.plans, indent=2),
        encoding="utf-8",
    )


def _predict_without_export_pool(
    predictor,
    *,
    args: argparse.Namespace,
    input_dir: Path,
    output_dir: Path,
    overwrite: bool,
    num_processes_preprocessing: int,
) -> None:
    import numpy as np
    import torch
    from batchgenerators.dataloading.multi_threaded_augmenter import MultiThreadedAugmenter
    from nnunetv2.inference.export_prediction import export_prediction_from_logits
    from nnunetv2.inference.sliding_window_prediction import compute_gaussian
    from nnunetv2.utilities.helpers import empty_cache

    list_of_lists_or_source_folder, output_filename_truncated, seg_from_prev_stage_files = (
        predictor._manage_input_and_output_lists(
            str(input_dir),
            str(output_dir),
            overwrite=overwrite,
            part_id=0,
            num_parts=1,
            save_probabilities=False,
        )
    )
    if len(list_of_lists_or_source_folder) == 0:
        return

    data_iterator = predictor._internal_get_data_iterator_from_lists_of_filenames(
        list_of_lists_or_source_folder,
        seg_from_prev_stage_files,
        output_filename_truncated,
        num_processes_preprocessing,
    )
    try:
        for preprocessed in data_iterator:
            data = preprocessed["data"]
            if isinstance(data, str):
                delfile = data
                data = torch.from_numpy(np.load(data))
                os.remove(delfile)

            ofile = preprocessed["ofile"]
            if ofile is None:
                raise RuntimeError("SpineLab sidecar inference requires explicit output files.")

            print(f"\nPredicting {Path(ofile).name}:")
            print(f"perform_everything_on_device: {predictor.perform_everything_on_device}")

            properties = preprocessed["data_properties"]
            device_name: str | None = None
            device_total_memory_bytes: int | None = None
            if predictor.device.type == "cuda":
                device_properties = torch.cuda.get_device_properties(predictor.device)
                device_name = device_properties.name
                device_total_memory_bytes = int(device_properties.total_memory)
            case_stem = _case_output_stem(Path(ofile))
            diagnostics_path = output_dir / f"{case_stem}.diagnostics.json"
            diagnostics = _build_case_diagnostics(
                case_id=case_stem,
                args=args,
                input_shape_cxyz=tuple(int(value) for value in data.shape),
                patch_size=tuple(
                    int(value) for value in predictor.configuration_manager.patch_size
                ),
                tile_step_size=float(predictor.tile_step_size),
                segmentation_heads=int(predictor.label_manager.num_segmentation_heads),
                use_mirroring=bool(predictor.use_mirroring),
                mirroring_axes=tuple(
                    int(value) for value in predictor.allowed_mirroring_axes or ()
                ),
                perform_everything_on_device=bool(predictor.perform_everything_on_device),
                output_file=diagnostics_path,
                properties=properties,
                device_name=device_name,
                device_total_memory_bytes=device_total_memory_bytes,
            )
            diagnostics_path.write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
            _emit_case_diagnostics(diagnostics)
            if args.fail_on_oversized_preflight:
                oversized_reason = _oversized_preflight_reason(diagnostics)
                if oversized_reason is not None:
                    print(oversized_reason)
                    raise OversizedPreflightError(oversized_reason)
            prediction = predictor.predict_logits_from_preprocessed_data(data).cpu()

            print("resampling and exporting prediction in-process")
            export_prediction_from_logits(
                prediction,
                properties,
                predictor.configuration_manager,
                predictor.plans_manager,
                predictor.dataset_json,
                ofile,
                False,
            )
            print(f"done with {Path(ofile).name}")
    finally:
        if isinstance(data_iterator, MultiThreadedAugmenter):
            data_iterator._finish()
        compute_gaussian.cache_clear()
        empty_cache(predictor.device)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _configure_environment(args)

    import torch
    from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor

    predictor = nnUNetPredictor(
        use_mirroring=not args.disable_tta,
        perform_everything_on_device=args.device == "cuda",
        device=torch.device(args.device),
        verbose=True,
    )
    predictor.initialize_from_trained_model_folder(
        str(args.model_dir),
        use_folds=(args.fold,),
        checkpoint_name=args.checkpoint,
    )
    _write_prediction_metadata(predictor, args)
    try:
        _predict_without_export_pool(
            predictor,
            args=args,
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            overwrite=not args.continue_prediction,
            num_processes_preprocessing=args.npp,
        )
    except OversizedPreflightError:
        return OVERSIZED_PREFLIGHT_EXIT_CODE
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
