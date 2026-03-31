from __future__ import annotations

import argparse
import sys
from pathlib import Path

from spinelab.io import CaseStore
from spinelab.segmentation import DEFAULT_NNUNET_FAMILY, install_nnunet_bundle
from spinelab.segmentation.bundles import DEFAULT_LEGACY_TRAINER_ROOT


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Import a local nnU-Net results directory into the SpineLab production "
            "segmentation bundle registry. This is the nnU-Net-specific wrapper; "
            "use tools/manage_segmentation_backends.py for the canonical multi-backend workflow."
        )
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=CaseStore().data_root,
        help="SpineLab data root that owns raw_test_data/models/segmentation.",
    )
    parser.add_argument(
        "--source-results-root",
        type=Path,
        default=DEFAULT_LEGACY_TRAINER_ROOT,
        help="nnU-Net trainer directory or parent results tree to import from.",
    )
    parser.add_argument(
        "--bundle-id",
        required=True,
        help="Stable bundle identifier. This becomes the installed bundle folder name.",
    )
    parser.add_argument(
        "--active-checkpoint-id",
        help=(
            "Checkpoint id to mark active in bundle.json. Required when the imported "
            "trainer tree contains multiple folds."
        ),
    )
    parser.add_argument(
        "--display-name",
        default="VERSe20 ResEnc Production",
        help="Human-readable display name shown in the Import workspace.",
    )
    parser.add_argument(
        "--family",
        default=DEFAULT_NNUNET_FAMILY,
        help="Model family identifier recorded in bundle.json provenance.",
    )
    parser.add_argument(
        "--activate",
        action="store_true",
        help="Mark the installed bundle as the active production bundle on this machine.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    store = CaseStore(args.data_root.resolve())
    bundle = install_nnunet_bundle(
        store=store,
        source_results_root=args.source_results_root.resolve(),
        bundle_id=args.bundle_id,
        active_checkpoint_id=args.active_checkpoint_id,
        display_name=args.display_name,
        family=args.family,
        activate=args.activate,
    )
    print(f"Installed bundle: {bundle.bundle_id}")
    print(f"Bundle directory: {bundle.bundle_dir}")
    print(f"Manifest: {bundle.manifest_path}")
    print(f"Active checkpoint: {bundle.active_checkpoint_id}")
    if args.activate:
        print("Bundle activated for production Analyze runs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
