from pathlib import Path

from PySide6.QtCore import QSettings

import spinelab.segmentation.bundles as bundles_module
from spinelab.io import CaseStore
from spinelab.segmentation import (
    DEBUG_SEGMENTATION_BUNDLES_ENV_VAR,
    DEFAULT_FOLD0_BUNDLE_ID,
    DEFAULT_FOLD1_BUNDLE_ID,
    SegmentationBundleRegistry,
    install_known_segmentation_backend,
    install_nnunet_bundle,
    install_skellytour_bundle,
    install_totalsegmentator_bundle,
)
from spinelab.services import SettingsService


def _settings_service(tmp_path: Path) -> SettingsService:
    service = SettingsService()
    service._settings = QSettings(  # pyright: ignore[reportPrivateUsage]
        str(tmp_path / "segmentation-bundles.ini"),
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
    (trainer_root / "fold_0" / "checkpoint_best.pth").write_bytes(b"checkpoint")
    (trainer_root / "fold_1" / "checkpoint_latest.pth").write_bytes(b"checkpoint")
    return trainer_root


def test_install_bundle_requires_explicit_active_checkpoint_for_multi_fold_source(
    tmp_path: Path,
) -> None:
    store = CaseStore(tmp_path / "data-root")
    settings = _settings_service(tmp_path)
    trainer_root = _write_fake_trainer_root(tmp_path)

    try:
        install_nnunet_bundle(
            store=store,
            source_results_root=trainer_root,
            bundle_id="VERSE20 ResEnc Fold 0",
            settings=settings,
            activate=True,
        )
    except ValueError as exc:
        assert "multiple folds" in str(exc)
        assert "active_checkpoint_id" in str(exc)
    else:
        raise AssertionError(
            "Expected multi-fold installs to require an explicit active_checkpoint_id."
        )


def test_install_bundle_copies_runtime_tree_and_resolves_active_checkpoint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = CaseStore(tmp_path / "data-root")
    settings = _settings_service(tmp_path)
    trainer_root = _write_fake_trainer_root(tmp_path)
    monkeypatch.setenv(DEBUG_SEGMENTATION_BUNDLES_ENV_VAR, "1")

    bundle = install_nnunet_bundle(
        store=store,
        source_results_root=trainer_root,
        bundle_id="VERSE20 ResEnc Fold 0",
        active_checkpoint_id="fold-0:checkpoint_final",
        settings=settings,
        activate=True,
    )
    registry = SegmentationBundleRegistry(store, settings=settings)
    resolved = registry.resolve_active_bundle()
    runtime_model = resolved.active_runtime_model()

    assert bundle.bundle_id == DEFAULT_FOLD0_BUNDLE_ID
    assert bundle.manifest_path.exists() is True
    assert resolved.bundle_id == bundle.bundle_id
    assert resolved.active_checkpoint_id == "fold-0:checkpoint_final"
    assert runtime_model.checkpoint_path.exists() is True
    assert runtime_model.runtime_results_root.exists() is True
    assert runtime_model.runtime_raw_root.exists() is True
    assert runtime_model.runtime_preprocessed_root.exists() is True
    assert runtime_model.label_mapping["C7"] == 1
    assert registry.production_status() == (bundle.display_name, "info")


def test_active_bundle_persists_across_registry_instances(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = CaseStore(tmp_path / "data-root")
    settings = _settings_service(tmp_path)
    trainer_root = _write_fake_trainer_root(tmp_path)
    monkeypatch.setenv(DEBUG_SEGMENTATION_BUNDLES_ENV_VAR, "1")

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
    registry = SegmentationBundleRegistry(store, settings=settings)

    assert registry.resolve_active_bundle().bundle_id == fold0_bundle.bundle_id

    registry.set_active_bundle_id(fold1_bundle.bundle_id)
    reloaded_registry = SegmentationBundleRegistry(store, settings=settings)

    assert reloaded_registry.resolve_active_bundle().bundle_id == fold1_bundle.bundle_id


def test_registry_defaults_to_skellytour_when_debug_bundles_are_quarantined(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = CaseStore(tmp_path / "data-root")
    settings = _settings_service(tmp_path)
    trainer_root = _write_fake_trainer_root(tmp_path)
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

    fold0_bundle = install_nnunet_bundle(
        store=store,
        source_results_root=trainer_root,
        bundle_id="VERSE20 ResEnc Fold 0",
        active_checkpoint_id="fold-0:checkpoint_final",
        settings=settings,
        activate=True,
    )
    skellytour_bundle = install_skellytour_bundle(
        store=store,
        bundle_id="SkellyTour",
        settings=settings,
        activate=False,
    )
    registry = SegmentationBundleRegistry(store, settings=settings)

    assert settings.load_active_segmentation_bundle_id() == fold0_bundle.bundle_id
    assert registry.resolve_active_bundle().bundle_id == fold0_bundle.bundle_id


def test_install_totalsegmentator_bundle_writes_runtime_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = CaseStore(tmp_path / "data-root")
    settings = _settings_service(tmp_path)
    monkeypatch.setattr(
        bundles_module,
        "_resolve_totalsegmentator_executable",
        lambda: r"C:\tools\TotalSegmentator.exe",
    )
    monkeypatch.setattr(
        bundles_module,
        "_detect_totalsegmentator_version",
        lambda: "2.12.0",
    )

    bundle = install_totalsegmentator_bundle(
        store=store,
        bundle_id="TotalSegmentator Baseline",
        settings=settings,
        activate=True,
    )
    registry = SegmentationBundleRegistry(store, settings=settings)
    runtime_model = registry.resolve_active_bundle().active_runtime_model()

    assert bundle.bundle_id == "totalsegmentator-baseline"
    assert bundle.driver_id == "totalsegmentator"
    assert bundle.active_checkpoint_id == "totalsegmentator-2.12.0"
    assert runtime_model.checkpoint_path.exists() is True
    assert "roi_subset=" in runtime_model.checkpoint_path.read_text(encoding="utf-8")


def test_install_skellytour_bundle_writes_runtime_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = CaseStore(tmp_path / "data-root")
    settings = _settings_service(tmp_path)
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

    bundle = install_skellytour_bundle(
        store=store,
        bundle_id="SkellyTour",
        settings=settings,
        activate=True,
    )
    registry = SegmentationBundleRegistry(store, settings=settings)
    runtime_model = registry.resolve_active_bundle().active_runtime_model()

    assert bundle.bundle_id == "skellytour"
    assert bundle.driver_id == "skellytour"
    assert bundle.active_checkpoint_id == "skellytour-high-0.0.2"
    assert runtime_model.checkpoint_path.exists() is True
    metadata = runtime_model.checkpoint_path.read_text(encoding="utf-8")
    assert "model=high" in metadata
    assert "executable=C:\\tools\\skellytour.exe" in metadata


def test_install_known_segmentation_backend_selects_expected_fold_checkpoint(
    tmp_path: Path,
) -> None:
    store = CaseStore(tmp_path / "data-root")
    settings = _settings_service(tmp_path)
    trainer_root = _write_fake_trainer_root(tmp_path)

    fold0_bundle = install_known_segmentation_backend(
        store=store,
        backend_id=DEFAULT_FOLD0_BUNDLE_ID,
        settings=settings,
        source_results_root=trainer_root,
    )
    fold1_bundle = install_known_segmentation_backend(
        store=store,
        backend_id=DEFAULT_FOLD1_BUNDLE_ID,
        settings=settings,
        source_results_root=trainer_root,
    )

    assert fold0_bundle.active_checkpoint_id == "fold-0:checkpoint_final"
    assert fold1_bundle.active_checkpoint_id == "fold-1:checkpoint_latest"
