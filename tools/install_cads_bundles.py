"""Install CADS composite segmentation bundles from downloaded model zips.

Extracts CADS pretrained nnU-Net model weights from zip archives into the
SpineLab bundle registry, and writes composite bundle.json manifests for
the CADS Skeleton and CADS Skeleton Plus configurations.

Usage:
  python tools/install_cads_bundles.py --zips-dir E:/data/CADS_data/pretrained_models
  python tools/install_cads_bundles.py --zips-dir E:/data/CADS_data/pretrained_models --activate skeleton
  python tools/install_cads_bundles.py --zips-dir E:/data/CADS_data/pretrained_models --activate skeleton-plus
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from spinelab.io import CaseStore
from spinelab.models.manifest import utc_now
from spinelab.segmentation.bundles import (
    BUNDLE_MANIFEST_NAME,
    CompositeSubModelSpec,
    InstalledSegmentationBundle,
    SegmentationBundleCheckpoint,
    SegmentationBundleInferenceSpec,
    SegmentationBundleRegistry,
)
from spinelab.segmentation.cads import (
    CADS_CHECKPOINT_NAME,
    CADS_CONFIGURATION,
    CADS_DRIVER_ID,
    CADS_ENVIRONMENT_ID,
    CADS_FAMILY,
    CADS_FOLD,
    CADS_PLAN_NAME,
    CADS_SKELETON_BUNDLE_ID,
    CADS_SKELETON_DISPLAY_NAME,
    CADS_SKELETON_LABEL_MAPPING,
    CADS_SKELETON_PLUS_BUNDLE_ID,
    CADS_SKELETON_PLUS_DISPLAY_NAME,
    CADS_SKELETON_PLUS_LABEL_MAPPING,
    CADS_SKELETON_PLUS_SUB_MODELS,
    CADS_SKELETON_SUB_MODELS,
    CADS_TRAINER_NAME,
    CADSSubModelSpec,
)


def _extract_task_model(
    zip_path: Path,
    target_results_root: Path,
) -> None:
    """Extract a CADS model zip into the bundle's nnunet_results directory."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            if member.startswith("__MACOSX") or member.endswith(".DS_Store"):
                continue
            zf.extract(member, target_results_root)
    print(f"  Extracted {zip_path.name}")


def _build_sub_model_specs(
    sub_models: tuple[CADSSubModelSpec, ...],
) -> tuple[CompositeSubModelSpec, ...]:
    """Convert CADSSubModelSpec to CompositeSubModelSpec for serialization."""
    return tuple(
        CompositeSubModelSpec(
            dataset_name=spec.dataset_name,
            trainer_name=CADS_TRAINER_NAME,
            plan_name=CADS_PLAN_NAME,
            configuration=CADS_CONFIGURATION,
            fold=CADS_FOLD,
            checkpoint_name=CADS_CHECKPOINT_NAME,
            label_cherry_pick=dict(spec.label_cherry_pick),
        )
        for spec in sub_models
    )


def _find_zip(zips_dir: Path, dataset_name: str) -> Path:
    """Find the zip file for a CADS dataset by name."""
    candidates = list(zips_dir.glob(f"{dataset_name}*.zip"))
    if not candidates:
        raise FileNotFoundError(
            f"Missing zip for {dataset_name} in {zips_dir}. "
            f"Download from https://github.com/murong-xu/CADS/releases/tag/cads-model_v1.0.0"
        )
    return candidates[0]


def install_cads_bundle(
    *,
    zips_dir: Path,
    registry: SegmentationBundleRegistry,
    bundle_id: str,
    display_name: str,
    sub_models: tuple[CADSSubModelSpec, ...],
    label_mapping: dict[str, int],
    activate: bool = False,
) -> InstalledSegmentationBundle:
    """Install a CADS composite bundle from zip archives."""
    bundle_dir = registry.bundle_dir(bundle_id)
    if bundle_dir.exists():
        print(f"Bundle {bundle_id} already exists at {bundle_dir}, skipping extraction.")
        print(f"  Delete the directory to reinstall.")
        return registry.load_bundle(bundle_id)

    registry.ensure_root()
    bundle_dir.mkdir(parents=True, exist_ok=True)
    results_root = bundle_dir / "nnunet_results"
    results_root.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "nnunet_raw").mkdir(parents=True, exist_ok=True)
    (bundle_dir / "nnunet_preprocessed").mkdir(parents=True, exist_ok=True)

    # Extract each task model
    seen_datasets: set[str] = set()
    for spec in sub_models:
        if spec.dataset_name in seen_datasets:
            continue
        seen_datasets.add(spec.dataset_name)
        zip_path = _find_zip(zips_dir, spec.dataset_name)
        _extract_task_model(zip_path, results_root)

    # Build composite sub-model specs
    composite_specs = _build_sub_model_specs(sub_models)

    # Use the first sub-model as the "primary" for inference_spec / checkpoint
    primary = sub_models[0]
    primary_dataset_name = primary.dataset_name
    trainer_dir = f"{CADS_TRAINER_NAME}__{CADS_PLAN_NAME}__{CADS_CONFIGURATION}"
    primary_checkpoint_rel = (
        f"nnunet_results/{primary_dataset_name}/{trainer_dir}/fold_{CADS_FOLD}/{CADS_CHECKPOINT_NAME}"
    )

    bundle = InstalledSegmentationBundle(
        bundle_id=bundle_id,
        family=CADS_FAMILY,
        display_name=display_name,
        environment_id=CADS_ENVIRONMENT_ID,
        driver_id=CADS_DRIVER_ID,
        modality="ct",
        inference_spec=SegmentationBundleInferenceSpec(
            dataset_id=int(primary_dataset_name.split("_")[0].removeprefix("Dataset")),
            dataset_name=primary_dataset_name.split("_", 1)[1],
            trainer_name=CADS_TRAINER_NAME,
            plan_name=CADS_PLAN_NAME,
            configuration=CADS_CONFIGURATION,
        ),
        checkpoints=(
            SegmentationBundleCheckpoint(
                checkpoint_id=f"composite-fold-{CADS_FOLD}",
                fold=CADS_FOLD,
                checkpoint_name=CADS_CHECKPOINT_NAME,
                relative_path=primary_checkpoint_rel,
            ),
        ),
        active_checkpoint_id=f"composite-fold-{CADS_FOLD}",
        label_mapping=label_mapping,
        provenance={
            "installed_at_utc": utc_now(),
            "source": "CADS pretrained models v1.0.0",
            "reference": "https://github.com/murong-xu/CADS",
            "license": "CC BY 4.0",
            "installer": "tools/install_cads_bundles.py",
        },
        runtime_root="nnunet_results",
        bundle_dir=bundle_dir,
        sub_models=composite_specs,
    )

    manifest_path = bundle_dir / BUNDLE_MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(bundle.to_dict(), indent=2),
        encoding="utf-8",
    )
    print(f"  Wrote {manifest_path}")

    if activate:
        registry.set_active_bundle_id(bundle_id)
        print(f"  Activated {bundle_id} as default segmentation backend")

    return bundle


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install CADS composite segmentation bundles",
    )
    parser.add_argument(
        "--zips-dir",
        type=Path,
        default=Path(r"E:\data\CADS_data\pretrained_models"),
        help="Directory containing CADS model zip files",
    )
    parser.add_argument(
        "--activate",
        choices=("skeleton", "skeleton-plus", "none"),
        default="skeleton",
        help="Which bundle to set as active after installation (default: skeleton)",
    )
    parser.add_argument(
        "--bundles",
        choices=("both", "skeleton", "skeleton-plus"),
        default="both",
        help="Which bundles to install (default: both)",
    )
    args = parser.parse_args()

    store = CaseStore()
    registry = SegmentationBundleRegistry(store)

    if args.bundles in ("both", "skeleton"):
        print(f"\nInstalling {CADS_SKELETON_DISPLAY_NAME}...")
        install_cads_bundle(
            zips_dir=args.zips_dir,
            registry=registry,
            bundle_id=CADS_SKELETON_BUNDLE_ID,
            display_name=CADS_SKELETON_DISPLAY_NAME,
            sub_models=CADS_SKELETON_SUB_MODELS,
            label_mapping=CADS_SKELETON_LABEL_MAPPING,
            activate=(args.activate == "skeleton"),
        )

    if args.bundles in ("both", "skeleton-plus"):
        print(f"\nInstalling {CADS_SKELETON_PLUS_DISPLAY_NAME}...")
        install_cads_bundle(
            zips_dir=args.zips_dir,
            registry=registry,
            bundle_id=CADS_SKELETON_PLUS_BUNDLE_ID,
            display_name=CADS_SKELETON_PLUS_DISPLAY_NAME,
            sub_models=CADS_SKELETON_PLUS_SUB_MODELS,
            label_mapping=CADS_SKELETON_PLUS_LABEL_MAPPING,
            activate=(args.activate == "skeleton-plus"),
        )

    print("\nDone. Installed bundles:")
    for bundle in registry.list_bundles():
        active = " (ACTIVE)" if registry.active_bundle_id() == bundle.bundle_id else ""
        print(f"  {bundle.bundle_id}: {bundle.display_name}{active}")


if __name__ == "__main__":
    main()
