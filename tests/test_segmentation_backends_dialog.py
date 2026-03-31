from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import QSettings

import spinelab.app.segmentation_backends_dialog as dialog_module
import spinelab.segmentation.bundles as bundles_module
from spinelab.app.segmentation_backends_dialog import SegmentationBackendsDialog
from spinelab.io import CaseStore
from spinelab.pipeline.device import RuntimeDeviceSelection
from spinelab.segmentation import (
    DEBUG_SEGMENTATION_BUNDLES_ENV_VAR,
    install_nnunet_bundle,
    install_skellytour_bundle,
)
from spinelab.services import SettingsService


def _settings_service(tmp_path: Path) -> SettingsService:
    service = SettingsService()
    service._settings = QSettings(  # pyright: ignore[reportPrivateUsage]
        str(tmp_path / "segmentation-backends-dialog.ini"),
        QSettings.Format.IniFormat,
    )
    return service


def _write_fake_trainer_root(tmp_path: Path) -> Path:
    trainer_root = (
        tmp_path
        / "legacy-results"
        / "Dataset321_VERSE20Vertebrae"
        / "nnUNetTrainer__nnUNetResEncL_24G__3d_fullres"
    )
    (trainer_root / "fold_0").mkdir(parents=True, exist_ok=True)
    (trainer_root / "fold_1").mkdir(parents=True, exist_ok=True)
    (trainer_root / "plans.json").write_text("{}", encoding="utf-8")
    (trainer_root / "dataset.json").write_text("{}", encoding="utf-8")
    (trainer_root / "fold_0" / "checkpoint_final.pth").write_bytes(b"checkpoint")
    (trainer_root / "fold_1" / "checkpoint_latest.pth").write_bytes(b"checkpoint")
    return trainer_root


def test_segmentation_backends_dialog_enumerates_and_activates_installed_bundles(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = CaseStore(tmp_path / "data-root")
    settings = _settings_service(tmp_path)
    trainer_root = _write_fake_trainer_root(tmp_path)
    fold0_bundle = install_nnunet_bundle(
        store=store,
        source_results_root=trainer_root,
        bundle_id="VERSE20 ResEnc Fold 0",
        active_checkpoint_id="fold-0:checkpoint_final",
        settings=settings,
        activate=True,
    )
    fold1_bundle = install_nnunet_bundle(
        store=store,
        source_results_root=trainer_root,
        bundle_id="VERSE20 ResEnc Fold 1",
        active_checkpoint_id="fold-1:checkpoint_latest",
        settings=settings,
        activate=False,
    )
    monkeypatch.setenv(DEBUG_SEGMENTATION_BUNDLES_ENV_VAR, "1")

    monkeypatch.setattr(
        dialog_module,
        "choose_runtime_device",
        lambda preferred_device=None: RuntimeDeviceSelection(
            requested_device="cuda",
            effective_device="cuda",
            backend="nvidia-cuda",
            cuda_version="12.4",
            gpu_name="Test GPU",
            total_vram_mb=81920,
            backend_health={"status": "ready"},
        ),
    )
    monkeypatch.setattr(
        dialog_module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, "ok", ""),
    )

    dialog = SegmentationBackendsDialog(store=store, settings=settings)
    qtbot.addWidget(dialog)

    assert dialog._table.rowCount() == 4
    assert dialog._active_label.text() == fold0_bundle.display_name
    assert dialog._table.item(0, 6).text() == "Active (Debug)"
    assert dialog._table.item(1, 6).text() == "Installed"
    assert dialog._table.item(2, 6).text() == "Not Installed"
    assert dialog._table.item(3, 6).text() == "Not Installed"

    dialog._table.selectRow(1)
    dialog._activate_selected_bundle()

    assert settings.load_active_segmentation_bundle_id() == fold1_bundle.bundle_id
    assert dialog._active_label.text() == fold1_bundle.display_name


def test_segmentation_backends_dialog_marks_nnunet_bundles_as_debug_only_by_default(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = CaseStore(tmp_path / "data-root")
    settings = _settings_service(tmp_path)
    trainer_root = _write_fake_trainer_root(tmp_path)
    monkeypatch.setattr(
        dialog_module,
        "choose_runtime_device",
        lambda preferred_device=None: RuntimeDeviceSelection(
            requested_device="cuda",
            effective_device="cuda",
            backend="nvidia-cuda",
            cuda_version="12.4",
            gpu_name="Test GPU",
            total_vram_mb=81920,
            backend_health={"status": "ready"},
        ),
    )
    monkeypatch.setattr(
        dialog_module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, "ok", ""),
    )
    install_nnunet_bundle(
        store=store,
        source_results_root=trainer_root,
        bundle_id="VERSE20 ResEnc Fold 0",
        active_checkpoint_id="fold-0:checkpoint_final",
        settings=settings,
        activate=True,
    )
    monkeypatch.setattr(
        bundles_module,
        "_resolve_skellytour_executable",
        lambda: r"C:\tools\skellytour.exe",
    )
    monkeypatch.setattr(
        bundles_module,
        "_detect_skellytour_version",
        lambda: "0.0.2",
    )
    install_skellytour_bundle(
        store=store,
        bundle_id="SkellyTour",
        settings=settings,
        activate=False,
    )

    dialog = SegmentationBackendsDialog(store=store, settings=settings)
    qtbot.addWidget(dialog)

    assert dialog._active_label.text() == "SkellyTour High"
    assert dialog._table.item(0, 6).text() == "Selected (Debug Only)"
    dialog._table.selectRow(0)
    assert dialog._activate_button.isEnabled() is False


def test_segmentation_backends_dialog_installs_selected_backend(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = CaseStore(tmp_path / "data-root")
    settings = _settings_service(tmp_path)
    installed_backend_ids: list[str] = []

    monkeypatch.setattr(
        dialog_module,
        "choose_runtime_device",
        lambda preferred_device=None: RuntimeDeviceSelection(
            requested_device="cuda",
            effective_device="cuda",
            backend="nvidia-cuda",
            cuda_version="12.4",
            gpu_name="Test GPU",
            total_vram_mb=81920,
            backend_health={"status": "ready"},
        ),
    )
    monkeypatch.setattr(
        dialog_module.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, "ok", ""),
    )
    monkeypatch.setattr(
        dialog_module,
        "install_known_segmentation_backend",
        lambda **kwargs: installed_backend_ids.append(kwargs["backend_id"]),
    )

    dialog = SegmentationBackendsDialog(store=store, settings=settings)
    qtbot.addWidget(dialog)

    dialog._table.selectRow(3)
    dialog._install_selected_backend()

    assert installed_backend_ids == ["skellytour"]
