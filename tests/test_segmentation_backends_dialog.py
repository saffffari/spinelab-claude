from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

from spinelab.app.segmentation_backends_dialog import SegmentationBackendsDialog
from spinelab.io import CaseStore
from spinelab.segmentation import install_nnunet_bundle
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


def test_segmentation_backends_dialog_lists_installed_bundles(
    qtbot,
    tmp_path: Path,
) -> None:
    store = CaseStore(tmp_path / "data-root")
    settings = _settings_service(tmp_path)
    trainer_root = _write_fake_trainer_root(tmp_path)
    install_nnunet_bundle(
        store=store,
        source_results_root=trainer_root,
        bundle_id="VERSE20 ResEnc Fold 0",
        active_checkpoint_id="fold-0:checkpoint_final",
        settings=settings,
        activate=True,
    )
    install_nnunet_bundle(
        store=store,
        source_results_root=trainer_root,
        bundle_id="VERSE20 ResEnc Fold 1",
        active_checkpoint_id="fold-1:checkpoint_latest",
        settings=settings,
        activate=False,
    )

    dialog = SegmentationBackendsDialog(store=store, settings=settings)
    qtbot.addWidget(dialog)

    assert len(dialog._cards) == 2  # pyright: ignore[reportPrivateUsage]


def test_segmentation_backends_dialog_activates_bundle_on_click(
    qtbot,
    tmp_path: Path,
) -> None:
    store = CaseStore(tmp_path / "data-root")
    settings = _settings_service(tmp_path)
    trainer_root = _write_fake_trainer_root(tmp_path)
    fold0 = install_nnunet_bundle(
        store=store,
        source_results_root=trainer_root,
        bundle_id="VERSE20 ResEnc Fold 0",
        active_checkpoint_id="fold-0:checkpoint_final",
        settings=settings,
        activate=True,
    )
    fold1 = install_nnunet_bundle(
        store=store,
        source_results_root=trainer_root,
        bundle_id="VERSE20 ResEnc Fold 1",
        active_checkpoint_id="fold-1:checkpoint_latest",
        settings=settings,
        activate=False,
    )

    dialog = SegmentationBackendsDialog(store=store, settings=settings)
    qtbot.addWidget(dialog)

    assert settings.load_active_segmentation_bundle_id() == fold0.bundle_id

    dialog._activate(fold1.bundle_id)  # pyright: ignore[reportPrivateUsage]

    assert settings.load_active_segmentation_bundle_id() == fold1.bundle_id
    cards = dialog._cards  # pyright: ignore[reportPrivateUsage]
    assert cards[0]._is_active is False  # pyright: ignore[reportPrivateUsage]
    assert cards[1]._is_active is True  # pyright: ignore[reportPrivateUsage]


def test_segmentation_backends_dialog_shows_empty_state(
    qtbot,
    tmp_path: Path,
) -> None:
    store = CaseStore(tmp_path / "data-root")
    settings = _settings_service(tmp_path)

    dialog = SegmentationBackendsDialog(store=store, settings=settings)
    qtbot.addWidget(dialog)

    assert len(dialog._cards) == 0  # pyright: ignore[reportPrivateUsage]
