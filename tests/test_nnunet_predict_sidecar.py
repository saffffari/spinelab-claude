from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_tool_module(module_path: Path, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def prepare_module() -> ModuleType:
    module_path = Path(__file__).resolve().parents[1] / "tools" / "nnunet_predict_sidecar.py"
    return load_tool_module(module_path, "nnunet_predict_sidecar_test")


def test_compute_sliding_window_steps_matches_known_fullres_case() -> None:
    module = prepare_module()

    steps = module._compute_sliding_window_steps(  # pyright: ignore[reportPrivateUsage]
        (769, 412, 328),
        (160, 192, 192),
        0.5,
    )

    assert [len(axis_steps) for axis_steps in steps] == [9, 4, 3]


def test_build_case_diagnostics_reports_high_window_pressure(tmp_path: Path) -> None:
    module = prepare_module()
    args = argparse.Namespace(
        fold="1",
        checkpoint="checkpoint_final.pth",
        device="cuda",
        model_dir=tmp_path / "model",
        results_root=tmp_path / "results",
        raw_root=tmp_path / "raw",
        preprocessed_root=tmp_path / "preprocessed",
        npp=12,
        nps=8,
    )

    diagnostics = module._build_case_diagnostics(  # pyright: ignore[reportPrivateUsage]
        case_id="normalized-volume",
        args=args,
        input_shape_cxyz=(1, 801, 865, 865),
        patch_size=(160, 192, 192),
        tile_step_size=0.5,
        segmentation_heads=27,
        use_mirroring=True,
        mirroring_axes=(0, 1, 2),
        perform_everything_on_device=True,
        output_file=tmp_path / "normalized-volume.diagnostics.json",
        properties={
            "shape_before_cropping": [801, 865, 865],
            "class_locations": {"1": [[0, 0, 0]]},
        },
        device_name="RTX 4090",
        device_total_memory_bytes=24 * 1024 * 1024 * 1024,
    )

    assert diagnostics["sliding_window"]["count"] == 810
    assert diagnostics["sliding_window"]["axis_step_counts"] == [10, 9, 9]
    assert diagnostics["inference"]["mirror_variant_count"] == 8
    assert diagnostics["estimates"]["results_arrays_exceed_total_device_memory"] is True
    assert any("device memory" in warning for warning in diagnostics["warnings"])
    assert diagnostics["data_properties"]["available_keys"] == [
        "class_locations",
        "shape_before_cropping",
    ]
    assert diagnostics["data_properties"]["selected"] == {
        "shape_before_cropping": [801, 865, 865],
    }


def test_oversized_preflight_reason_blocks_when_results_arrays_exceed_device_memory(
    tmp_path: Path,
) -> None:
    module = prepare_module()
    args = argparse.Namespace(
        fold="1",
        checkpoint="checkpoint_final.pth",
        device="cuda",
        model_dir=tmp_path / "model",
        results_root=tmp_path / "results",
        raw_root=tmp_path / "raw",
        preprocessed_root=tmp_path / "preprocessed",
        npp=12,
        nps=8,
    )

    diagnostics = module._build_case_diagnostics(  # pyright: ignore[reportPrivateUsage]
        case_id="normalized-volume",
        args=args,
        input_shape_cxyz=(1, 865, 907, 907),
        patch_size=(160, 192, 192),
        tile_step_size=0.5,
        segmentation_heads=27,
        use_mirroring=True,
        mirroring_axes=(0, 1, 2),
        perform_everything_on_device=True,
        output_file=tmp_path / "normalized-volume.diagnostics.json",
        properties={},
        device_name="RTX 4090",
        device_total_memory_bytes=24 * 1024 * 1024 * 1024,
    )

    reason = module._oversized_preflight_reason(diagnostics)  # pyright: ignore[reportPrivateUsage]

    assert reason is not None
    assert "results arrays" in reason
    assert "device memory" in reason

