from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import spinelab.pipeline.stages.registration as registration_module
from spinelab.pipeline.stages.common import homogeneous_transform, rotation_matrix_xyz


def test_transform_axis_aligned_extents_accounts_for_rotation() -> None:
    transform = homogeneous_transform(
        rotation_matrix_xyz(ry_degrees=90.0),
        (0.0, 0.0, 0.0),
    )

    extents = registration_module._transform_axis_aligned_extents(
        transform,
        (10.0, 2.0, 4.0),
    )

    assert extents == pytest.approx([4.0, 2.0, 10.0])


def test_spinelab_app_import_is_lazy_for_main_window(monkeypatch: pytest.MonkeyPatch) -> None:
    del monkeypatch
    repo_root = Path(__file__).resolve().parents[1]
    code = """
import sys
import spinelab.app as app
print('before=' + str('spinelab.app.main_window' in sys.modules))
_ = app.MainWindow
print('after=' + str('spinelab.app.main_window' in sys.modules))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
        text=True,
    )

    assert "before=False" in completed.stdout
    assert "after=True" in completed.stdout


def test_spinelab_main_import_does_not_eagerly_import_main_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del monkeypatch
    repo_root = Path(__file__).resolve().parents[1]
    code = """
import sys
import spinelab.main
print('loaded=' + str('spinelab.app.main_window' in sys.modules))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(repo_root),
        check=True,
        capture_output=True,
        text=True,
    )

    assert "loaded=False" in completed.stdout
