from __future__ import annotations

import importlib.util
import json
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


def gate_module() -> ModuleType:
    module_path = Path(__file__).resolve().parents[1] / "tools" / "nnunet_verse20_post_fold_gate.py"
    return load_tool_module(module_path, "nnunet_verse20_post_fold_gate_test")


def write_gate_inputs(
    tmp_path: Path,
    *,
    include_checkpoint_final: bool = True,
    include_checkpoint_best: bool = True,
    include_validation_summary: bool = True,
    foreground_dice: float = 0.82,
    log_text: str = (
        "2026-03-25 17:15:08.965039: Epoch 303\n"
        "2026-03-25 17:15:09.000000: New best EMA pseudo Dice: 0.8123\n"
    ),
) -> Path:
    fold_dir = tmp_path / "fold_0"
    validation_dir = fold_dir / "validation"
    validation_dir.mkdir(parents=True)

    if include_checkpoint_final:
        (fold_dir / "checkpoint_final.pth").write_text("final", encoding="utf-8")
    if include_checkpoint_best:
        (fold_dir / "checkpoint_best.pth").write_text("best", encoding="utf-8")
    (fold_dir / "training_log_2026_3_25_10_24_19.txt").write_text(log_text, encoding="utf-8")
    if include_validation_summary:
        payload = {"foreground_mean": {"Dice": foreground_dice}}
        (validation_dir / "summary.json").write_text(json.dumps(payload), encoding="utf-8")
    return fold_dir


def test_post_fold_gate_passes_for_healthy_fold(tmp_path: Path) -> None:
    module = gate_module()
    fold_dir = write_gate_inputs(tmp_path)

    exit_code = module.main(["--fold-dir", str(fold_dir)])

    assert exit_code == 0
    summary_path = fold_dir / "post_fold" / "fold_0_gate_summary.json"
    markdown_path = fold_dir / "post_fold" / "fold_0_gate_summary.md"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["foreground_mean_dice"] == 0.82
    assert payload["max_ema_pseudo_dice"] == 0.8123
    assert markdown_path.exists()


def test_post_fold_gate_fails_without_checkpoint_final(tmp_path: Path) -> None:
    module = gate_module()
    fold_dir = write_gate_inputs(tmp_path, include_checkpoint_final=False)

    exit_code = module.main(["--fold-dir", str(fold_dir)])

    assert exit_code == 1
    payload = json.loads(
        (fold_dir / "post_fold" / "fold_0_gate_summary.json").read_text(encoding="utf-8")
    )
    assert payload["passed"] is False
    assert any("checkpoint_final.pth" in reason for reason in payload["reasons"])


def test_post_fold_gate_fails_without_validation_summary(tmp_path: Path) -> None:
    module = gate_module()
    fold_dir = write_gate_inputs(tmp_path, include_validation_summary=False)

    exit_code = module.main(["--fold-dir", str(fold_dir)])

    assert exit_code == 1
    payload = json.loads(
        (fold_dir / "post_fold" / "fold_0_gate_summary.json").read_text(encoding="utf-8")
    )
    assert any("validation summary" in reason for reason in payload["reasons"])


def test_post_fold_gate_fails_on_fatal_log_markers(tmp_path: Path) -> None:
    module = gate_module()
    fold_dir = write_gate_inputs(
        tmp_path,
        log_text=(
            "2026-03-25 17:15:08.965039: Epoch 303\n"
            "RuntimeError: CUDA out of memory\n"
        ),
    )

    exit_code = module.main(["--fold-dir", str(fold_dir)])

    assert exit_code == 1
    payload = json.loads(
        (fold_dir / "post_fold" / "fold_0_gate_summary.json").read_text(encoding="utf-8")
    )
    assert "RuntimeError" in payload["fatal_log_markers"]
    assert any("fatal markers" in reason for reason in payload["reasons"])


def test_post_fold_gate_fails_on_low_foreground_dice(tmp_path: Path) -> None:
    module = gate_module()
    fold_dir = write_gate_inputs(tmp_path, foreground_dice=0.63)

    exit_code = module.main(["--fold-dir", str(fold_dir)])

    assert exit_code == 1
    payload = json.loads(
        (fold_dir / "post_fold" / "fold_0_gate_summary.json").read_text(encoding="utf-8")
    )
    assert payload["foreground_mean_dice"] == 0.63
    assert any("below gate" in reason for reason in payload["reasons"])
