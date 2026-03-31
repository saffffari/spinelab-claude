from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from spinelab.io import CaseStore
from spinelab.pipeline.backends import BACKEND_ADAPTERS
from spinelab.pipeline.device import choose_runtime_device
from spinelab.segmentation import (
    DEFAULT_LEGACY_TRAINER_ROOT,
    KNOWN_SEGMENTATION_BACKENDS,
    SegmentationBundleRegistry,
    install_known_segmentation_backend,
    known_segmentation_backend,
    map_installed_bundles_to_known_backends,
)

_ADAPTERS_BY_TOOL = {adapter.spec.tool_name: adapter for adapter in BACKEND_ADAPTERS}
_BACKEND_CHOICES = tuple(backend.backend_id for backend in KNOWN_SEGMENTATION_BACKENDS)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "List, install, and activate workstation-level SpineLab segmentation "
            "evaluation backends."
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
        help="nnU-Net trainer directory or parent results tree used for fold installs.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="Show the canonical backend matrix and active selection.")
    subparsers.add_parser("status", help="Alias for list.")

    install_parser = subparsers.add_parser("install", help="Install or register one backend.")
    install_parser.add_argument("backend_id", choices=_BACKEND_CHOICES)
    install_parser.add_argument(
        "--activate",
        action="store_true",
        help="Activate the backend after installing or registering it.",
    )

    activate_parser = subparsers.add_parser(
        "activate",
        help="Switch Analyze to an already installed backend.",
    )
    activate_parser.add_argument("backend_id", choices=_BACKEND_CHOICES)
    return parser.parse_args(argv)


def _environment_health(driver_id: str) -> str:
    adapter = _ADAPTERS_BY_TOOL.get(driver_id)
    if adapter is None:
        return "unknown"
    if adapter.spec.required_device.value == "cuda":
        runtime = choose_runtime_device("cuda")
        if runtime.effective_device != "cuda":
            return "cuda-unavailable"
    try:
        completed = subprocess.run(
            adapter.healthcheck_command(),
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except OSError as exc:
        return f"unavailable ({exc})"
    except subprocess.TimeoutExpired:
        return "healthcheck-timeout"
    if completed.returncode == 0:
        return "ready"
    stderr = (completed.stderr or completed.stdout or "").strip().splitlines()
    if stderr:
        return f"unavailable ({stderr[-1][:60]})"
    return f"unavailable (exit {completed.returncode})"


def _print_backend_matrix(*, store: CaseStore) -> int:
    registry = SegmentationBundleRegistry(store)
    installed_by_id = map_installed_bundles_to_known_backends(registry.list_bundles())
    active_bundle_id = registry.active_bundle_id()
    print(f"Active backend: {active_bundle_id or 'none'}")
    print("backend_id\tstatus\tenvironment\tcheckpoint\tdisplay_name")
    for backend in KNOWN_SEGMENTATION_BACKENDS:
        bundle = installed_by_id.get(backend.backend_id)
        checkpoint_id = bundle.active_checkpoint().checkpoint_id if bundle is not None else "-"
        status = (
            "active"
            if bundle is not None and bundle.bundle_id == active_bundle_id
            else "installed"
            if bundle is not None
            else "not-installed"
        )
        display_name = bundle.display_name if bundle is not None else backend.display_name
        print(
            "\t".join(
                (
                    backend.backend_id,
                    status,
                    _environment_health(backend.driver_id),
                    checkpoint_id,
                    display_name,
                )
            )
        )
    return 0


def _install_backend(
    *,
    store: CaseStore,
    backend_id: str,
    source_results_root: Path,
    activate: bool,
) -> int:
    bundle = install_known_segmentation_backend(
        store=store,
        backend_id=backend_id,
        source_results_root=source_results_root.resolve(),
        activate=activate,
    )
    print(f"Installed backend: {bundle.bundle_id}")
    print(f"Bundle directory: {bundle.bundle_dir}")
    print(f"Active checkpoint: {bundle.active_checkpoint_id}")
    if activate:
        print("Backend activated for Analyze.")
    return 0


def _activate_backend(*, store: CaseStore, backend_id: str) -> int:
    registry = SegmentationBundleRegistry(store)
    backend = known_segmentation_backend(backend_id)
    bundle = map_installed_bundles_to_known_backends(registry.list_bundles()).get(
        backend.backend_id
    )
    if bundle is None:
        raise FileNotFoundError(
            f"Backend {backend.backend_id!r} is not installed. Run the install command first."
        )
    registry.set_active_bundle_id(bundle.bundle_id)
    print(f"Activated backend: {bundle.bundle_id}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    store = CaseStore(args.data_root.resolve())

    if args.command in {"list", "status"}:
        return _print_backend_matrix(store=store)
    if args.command == "install":
        return _install_backend(
            store=store,
            backend_id=args.backend_id,
            source_results_root=args.source_results_root,
            activate=bool(args.activate),
        )
    if args.command == "activate":
        return _activate_backend(store=store, backend_id=args.backend_id)
    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
