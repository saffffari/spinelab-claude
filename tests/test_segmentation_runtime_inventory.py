from __future__ import annotations

from pathlib import Path


def test_tools_directory_exposes_only_current_inference_entrypoint() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    tool_names = {path.name for path in (repo_root / "tools").glob("run_*_inference.py")}
    assert tool_names == {"run_verse20_inference.py"}


def test_pipeline_backend_directory_exposes_only_current_adapters() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    backend_names = {
        path.stem
        for path in (repo_root / "src" / "spinelab" / "pipeline" / "backends").glob("*.py")
        if path.name != "__init__.py"
    }
    assert backend_names == {
        "base",
        "landmark_point_transformer",
        "nanodrr",
        "nnunet",
        "polypose",
        "skellytour",
        "totalsegmentator",
    }
