from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

from spinelab.io import CaseStore
from spinelab.models.manifest import utc_now
from spinelab.ontology import STANDARD_STRUCTURES
from spinelab.services import SettingsService

DEFAULT_NNUNET_FAMILY = "nnunet-verse20-resenc"
DEFAULT_NNUNET_ENVIRONMENT_ID = "nnunet-verse20-win"
DEFAULT_NNUNET_RUNTIME_ROOT = "nnunet_results"
DEFAULT_NNUNET_RAW_ROOT = "nnunet_raw"
DEFAULT_NNUNET_PREPROCESSED_ROOT = "nnunet_preprocessed"
DEFAULT_NNUNET_DRIVER_ID = "nnunetv2"
DEFAULT_FOLD0_BUNDLE_ID = "verse20-resenc-fold0"
DEFAULT_FOLD0_DISPLAY_NAME = "VERSe20 ResEnc Fold 0"
DEFAULT_FOLD1_BUNDLE_ID = "verse20-resenc-fold1"
DEFAULT_FOLD1_DISPLAY_NAME = "VERSe20 ResEnc Fold 1"
DEFAULT_BUNDLE_MODALITY = "ct"
DEFAULT_PRODUCTION_BUNDLE_ID = DEFAULT_FOLD0_BUNDLE_ID
DEBUG_SEGMENTATION_BUNDLES_ENV_VAR = "SPINELAB_ENABLE_DEBUG_SEGMENTATION_BUNDLES"
BUNDLE_MANIFEST_NAME = "bundle.json"
DEFAULT_DISPLAY_NAME = "VERSe20 ResEnc Production"
DEFAULT_LEGACY_TRAINER_ROOT = Path(
    r"D:\dev\spinelab_data\nnunet\results"
    r"\Dataset321_VERSE20Vertebrae"
    r"\nnUNetTrainer__nnUNetResEncL_24G__3d_fullres"
)
_CHECKPOINT_PRIORITY = {
    "checkpoint_final.pth": 0,
    "checkpoint_best.pth": 1,
    "checkpoint_latest.pth": 2,
}
DEFAULT_LABEL_MAPPING = {
    definition.standard_level_id: index + 1
    for index, definition in enumerate(STANDARD_STRUCTURES)
}
DEBUG_ONLY_SEGMENTATION_BACKEND_IDS: frozenset[str] = frozenset()
PRODUCTION_SEGMENTATION_BACKEND_PRIORITY = (
    DEFAULT_PRODUCTION_BUNDLE_ID,
)


def _sanitize_bundle_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return normalized.strip("-")


def _env_flag_enabled(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _copy_file_or_hardlink(source: str, destination: str) -> str:
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)
    return destination


def _resolve_conda_executable() -> str | None:
    conda_executable = os.environ.get("CONDA_EXE")
    if conda_executable:
        candidate = Path(conda_executable)
        if candidate.exists():
            return str(candidate)
    return shutil.which("conda")


def _candidate_conda_roots(conda_executable: str) -> tuple[Path, ...]:
    resolved = Path(conda_executable).resolve()
    parents: list[Path] = []
    if resolved.parent.name.lower() in {"scripts", "condabin"}:
        parents.append(resolved.parent.parent)
    parents.append(resolved.parent)
    ordered: list[Path] = []
    seen: set[Path] = set()
    for candidate in parents:
        if candidate not in seen:
            ordered.append(candidate)
            seen.add(candidate)
    return tuple(ordered)


def _resolve_env_python_executable(
    *,
    conda_executable: str,
    conda_env_name: str,
) -> Path | None:
    for root in _candidate_conda_roots(conda_executable):
        base_python = root / "python.exe"
        if root.name.lower() == conda_env_name.lower() and base_python.exists():
            return base_python
        env_python = root / "envs" / conda_env_name / "python.exe"
        if env_python.exists():
            return env_python
    return None


def _resolve_environment_executable(
    *,
    environment_id: str,
    executable_names: tuple[str, ...],
) -> str | None:
    conda_executable = _resolve_conda_executable()
    if conda_executable is not None:
        env_python = _resolve_env_python_executable(
            conda_executable=conda_executable,
            conda_env_name=environment_id,
        )
        if env_python is not None:
            env_root = env_python.parent
            for executable_name in executable_names:
                for candidate in (
                    env_root / "Scripts" / executable_name,
                    env_root / "Scripts" / f"{executable_name}.exe",
                    env_root / executable_name,
                    env_root / f"{executable_name}.exe",
                ):
                    if candidate.exists():
                        return str(candidate)
    for executable_name in executable_names:
        for candidate_path in (
            shutil.which(executable_name),
            shutil.which(f"{executable_name}.exe"),
        ):
            if candidate_path:
                return candidate_path
    return None


def _detect_package_version_from_environment(
    *,
    environment_id: str,
    package_names: tuple[str, ...],
) -> str:
    conda_executable = _resolve_conda_executable()
    if conda_executable is None:
        return "unknown"
    env_python = _resolve_env_python_executable(
        conda_executable=conda_executable,
        conda_env_name=environment_id,
    )
    python_command = (
        [str(env_python)]
        if env_python is not None
        else [conda_executable, "run", "-n", environment_id, "python"]
    )
    version_script = (
        "import importlib.metadata as metadata, sys; "
        "packages = [item for item in sys.argv[1:] if item]; "
        "version = 'unknown'; "
        "for package in packages:\n"
        "    try:\n"
        "        version = metadata.version(package)\n"
        "        break\n"
        "    except metadata.PackageNotFoundError:\n"
        "        pass\n"
        "print(version)"
    )
    completed = subprocess.run(
        [*python_command, "-c", version_script, *package_names],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return "unknown"
    version = completed.stdout.strip()
    return version or "unknown"


@dataclass(frozen=True, slots=True)
class KnownSegmentationBackend:
    backend_id: str
    display_name: str
    family: str
    driver_id: str
    environment_id: str
    modality: str = DEFAULT_BUNDLE_MODALITY
    description: str = ""


KNOWN_SEGMENTATION_BACKENDS = (
    KnownSegmentationBackend(
        backend_id=DEFAULT_FOLD0_BUNDLE_ID,
        display_name=DEFAULT_FOLD0_DISPLAY_NAME,
        family=DEFAULT_NNUNET_FAMILY,
        driver_id=DEFAULT_NNUNET_DRIVER_ID,
        environment_id=DEFAULT_NNUNET_ENVIRONMENT_ID,
        description="Local VERSe20 residual-encoder fold 0 bundle.",
    ),
    KnownSegmentationBackend(
        backend_id=DEFAULT_FOLD1_BUNDLE_ID,
        display_name=DEFAULT_FOLD1_DISPLAY_NAME,
        family=DEFAULT_NNUNET_FAMILY,
        driver_id=DEFAULT_NNUNET_DRIVER_ID,
        environment_id=DEFAULT_NNUNET_ENVIRONMENT_ID,
        description="Local VERSe20 residual-encoder fold 1 bundle.",
    ),
)


def _canonical_backend_id(value: str) -> str | None:
    normalized_value = _sanitize_bundle_id(value)
    if not normalized_value:
        return None
    for backend in KNOWN_SEGMENTATION_BACKENDS:
        if normalized_value in {
            backend.backend_id,
            _sanitize_bundle_id(backend.display_name),
        }:
            return backend.backend_id
    return None


def _normalize_bundle_id(value: str) -> str:
    canonical_backend_id = _canonical_backend_id(value)
    if canonical_backend_id is not None:
        return canonical_backend_id
    return _sanitize_bundle_id(value)


def normalize_bundle_id(value: str) -> str:
    return _normalize_bundle_id(value)


def debug_segmentation_bundles_enabled() -> bool:
    return _env_flag_enabled(os.environ.get(DEBUG_SEGMENTATION_BUNDLES_ENV_VAR))


def is_debug_only_bundle_id(value: str) -> bool:
    normalized_value = _canonical_backend_id(value) or _normalize_bundle_id(value)
    return normalized_value in DEBUG_ONLY_SEGMENTATION_BACKEND_IDS


@dataclass(frozen=True, slots=True)
class SegmentationBundleInferenceSpec:
    dataset_id: int
    dataset_name: str
    trainer_name: str
    plan_name: str
    configuration: str

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> SegmentationBundleInferenceSpec:
        raw_dataset_id = payload.get("dataset_id", 0)
        try:
            dataset_id = int(str(raw_dataset_id))
        except ValueError:
            dataset_id = 0
        return cls(
            dataset_id=dataset_id,
            dataset_name=str(payload.get("dataset_name", "")),
            trainer_name=str(payload.get("trainer_name", "")),
            plan_name=str(payload.get("plan_name", "")),
            configuration=str(payload.get("configuration", "")),
        )


@dataclass(frozen=True, slots=True)
class SegmentationBundleCheckpoint:
    checkpoint_id: str
    fold: str
    checkpoint_name: str
    relative_path: str

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> SegmentationBundleCheckpoint:
        return cls(
            checkpoint_id=str(payload.get("checkpoint_id", "")),
            fold=str(payload.get("fold", "")),
            checkpoint_name=str(payload.get("checkpoint_name", "")),
            relative_path=str(payload.get("relative_path", "")),
        )


@dataclass(frozen=True, slots=True)
class SegmentationRuntimeModel:
    model_id: str
    display_name: str
    family: str
    driver_id: str
    environment_id: str
    modality: str
    inference_spec: SegmentationBundleInferenceSpec
    checkpoint: SegmentationBundleCheckpoint
    runtime_results_root: Path
    checkpoint_path: Path
    label_mapping: dict[str, int]
    provenance: dict[str, str]

    @property
    def runtime_bundle_root(self) -> Path:
        return self.runtime_results_root.parent

    @property
    def runtime_raw_root(self) -> Path:
        return self.runtime_bundle_root / DEFAULT_NNUNET_RAW_ROOT

    @property
    def runtime_preprocessed_root(self) -> Path:
        return self.runtime_bundle_root / DEFAULT_NNUNET_PREPROCESSED_ROOT


@dataclass(frozen=True, slots=True)
class InstalledSegmentationBundle:
    bundle_id: str
    family: str
    display_name: str
    environment_id: str
    driver_id: str
    modality: str
    inference_spec: SegmentationBundleInferenceSpec
    checkpoints: tuple[SegmentationBundleCheckpoint, ...]
    active_checkpoint_id: str
    label_mapping: dict[str, int]
    provenance: dict[str, str]
    runtime_root: str
    bundle_dir: Path

    @property
    def manifest_path(self) -> Path:
        return self.bundle_dir / BUNDLE_MANIFEST_NAME

    @property
    def runtime_results_root(self) -> Path:
        return self.bundle_dir / self.runtime_root

    def active_checkpoint(self) -> SegmentationBundleCheckpoint:
        for checkpoint in self.checkpoints:
            if checkpoint.checkpoint_id == self.active_checkpoint_id:
                return checkpoint
        raise ValueError(
            f"Bundle {self.bundle_id} is missing active checkpoint {self.active_checkpoint_id!r}."
        )

    def active_runtime_model(self) -> SegmentationRuntimeModel:
        checkpoint = self.active_checkpoint()
        checkpoint_path = (self.bundle_dir / checkpoint.relative_path).resolve()
        return SegmentationRuntimeModel(
            model_id=self.bundle_id,
            display_name=self.display_name,
            family=self.family,
            driver_id=self.driver_id,
            environment_id=self.environment_id,
            modality=self.modality,
            inference_spec=self.inference_spec,
            checkpoint=checkpoint,
            runtime_results_root=self.runtime_results_root.resolve(),
            checkpoint_path=checkpoint_path,
            label_mapping=dict(self.label_mapping),
            provenance=dict(self.provenance),
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "bundle_id": self.bundle_id,
            "family": self.family,
            "display_name": self.display_name,
            "environment_id": self.environment_id,
            "driver_id": self.driver_id,
            "modality": self.modality,
            "inference_spec": asdict(self.inference_spec),
            "checkpoints": [asdict(checkpoint) for checkpoint in self.checkpoints],
            "active_checkpoint_id": self.active_checkpoint_id,
            "label_mapping": dict(self.label_mapping),
            "provenance": dict(self.provenance),
            "runtime_root": self.runtime_root,
        }
        return payload

    @classmethod
    def from_dict(
        cls,
        payload: dict[str, object],
        *,
        bundle_dir: Path,
    ) -> InstalledSegmentationBundle:
        raw_checkpoints = payload.get("checkpoints", [])
        checkpoint_payloads = raw_checkpoints if isinstance(raw_checkpoints, list) else []
        checkpoints = tuple(
            SegmentationBundleCheckpoint.from_dict(item)
            for item in checkpoint_payloads
            if isinstance(item, dict)
        )
        raw_label_mapping = payload.get("label_mapping", {})
        label_mapping: dict[str, int] = {}
        if isinstance(raw_label_mapping, dict):
            for vertebra_id, label_value in raw_label_mapping.items():
                try:
                    label_mapping[str(vertebra_id)] = int(label_value)
                except (TypeError, ValueError):
                    continue
        raw_provenance = payload.get("provenance", {})
        provenance = (
            {str(key): str(value) for key, value in raw_provenance.items()}
            if isinstance(raw_provenance, dict)
            else {}
        )
        raw_inference_spec = payload.get("inference_spec", {})
        inference_spec_payload = raw_inference_spec if isinstance(raw_inference_spec, dict) else {}
        return cls(
            bundle_id=str(payload.get("bundle_id", bundle_dir.name)),
            family=str(payload.get("family", DEFAULT_NNUNET_FAMILY)),
            display_name=str(payload.get("display_name", bundle_dir.name)),
            environment_id=str(payload.get("environment_id", DEFAULT_NNUNET_ENVIRONMENT_ID)),
            driver_id=str(payload.get("driver_id", DEFAULT_NNUNET_DRIVER_ID)),
            modality=str(payload.get("modality", DEFAULT_BUNDLE_MODALITY)),
            inference_spec=SegmentationBundleInferenceSpec.from_dict(inference_spec_payload),
            checkpoints=checkpoints,
            active_checkpoint_id=str(payload.get("active_checkpoint_id", "")),
            label_mapping=label_mapping,
            provenance=provenance,
            runtime_root=str(payload.get("runtime_root", DEFAULT_NNUNET_RUNTIME_ROOT)),
            bundle_dir=bundle_dir,
        )


class SegmentationBundleRegistry:
    def __init__(
        self,
        store: CaseStore,
        settings: SettingsService | None = None,
    ) -> None:
        self._store = store
        self._settings = settings or SettingsService()

    @property
    def bundles_root(self) -> Path:
        return self._store.raw_test_data_root / "models" / "segmentation"

    def ensure_root(self) -> Path:
        root = self.bundles_root
        root.mkdir(parents=True, exist_ok=True)
        return root

    def bundle_dir(self, bundle_id: str) -> Path:
        return self.bundles_root / bundle_id

    def bundle_manifest_path(self, bundle_id: str) -> Path:
        return self.bundle_dir(bundle_id) / BUNDLE_MANIFEST_NAME

    def _find_bundle_manifest_path(self, bundle_id: str) -> Path | None:
        direct_manifest_path = self.bundle_manifest_path(bundle_id)
        if direct_manifest_path.exists():
            return direct_manifest_path
        if not self.bundles_root.exists():
            return None
        normalized_bundle_id = _normalize_bundle_id(bundle_id)
        for manifest_path in sorted(
            self.bundles_root.glob(f"*/{BUNDLE_MANIFEST_NAME}"),
            key=lambda path: path.parent.name.lower(),
        ):
            if _normalize_bundle_id(manifest_path.parent.name) == normalized_bundle_id:
                return manifest_path
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            manifest_bundle_id = payload.get("bundle_id")
            if isinstance(manifest_bundle_id, str) and (
                _normalize_bundle_id(manifest_bundle_id) == normalized_bundle_id
            ):
                return manifest_path
            display_name = payload.get("display_name")
            if isinstance(display_name, str) and (
                _normalize_bundle_id(display_name) == normalized_bundle_id
            ):
                return manifest_path
        return None

    def list_bundles(self) -> list[InstalledSegmentationBundle]:
        if not self.bundles_root.exists():
            return []
        bundles: list[InstalledSegmentationBundle] = []
        for manifest_path in sorted(
            self.bundles_root.glob(f"*/{BUNDLE_MANIFEST_NAME}"),
            key=lambda path: path.parent.name.lower(),
        ):
            bundles.append(self.load_bundle(manifest_path.parent.name))
        return bundles

    def load_bundle(self, bundle_id: str) -> InstalledSegmentationBundle:
        manifest_path = self._find_bundle_manifest_path(bundle_id)
        if manifest_path is None:
            raise FileNotFoundError(f"Segmentation bundle is missing: {bundle_id}")
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid bundle manifest at {manifest_path}")
        bundle = InstalledSegmentationBundle.from_dict(payload, bundle_dir=manifest_path.parent)
        if not bundle.checkpoints:
            raise ValueError(f"Segmentation bundle exposes no checkpoints: {bundle.bundle_id}")
        return bundle

    def active_bundle_id(self) -> str | None:
        bundle_id = self._settings.load_active_segmentation_bundle_id()
        if bundle_id is None:
            return None
        return _normalize_bundle_id(bundle_id)

    def set_active_bundle_id(self, bundle_id: str | None) -> None:
        if bundle_id:
            self._settings.save_active_segmentation_bundle_id(
                _normalize_bundle_id(bundle_id)
            )
            return
        self._settings.clear_active_segmentation_bundle_id()

    def preferred_production_bundle_id(self) -> str | None:
        installed_by_id = map_installed_bundles_to_known_backends(self.list_bundles())
        configured_bundle_id = self.active_bundle_id()
        if configured_bundle_id and not is_debug_only_bundle_id(configured_bundle_id):
            configured_bundle = installed_by_id.get(configured_bundle_id)
            if configured_bundle is not None:
                return configured_bundle.bundle_id
            try:
                return self.load_bundle(configured_bundle_id).bundle_id
            except Exception:
                pass
        for candidate_id in PRODUCTION_SEGMENTATION_BACKEND_PRIORITY:
            bundle = installed_by_id.get(candidate_id)
            if bundle is not None:
                return bundle.bundle_id
        return None

    def resolved_active_bundle_id(
        self,
        *,
        allow_debug_bundles: bool | None = None,
    ) -> str | None:
        try:
            return self.resolve_active_bundle(
                allow_debug_bundles=allow_debug_bundles
            ).bundle_id
        except Exception:
            return None

    def resolve_active_bundle(
        self,
        *,
        allow_debug_bundles: bool | None = None,
    ) -> InstalledSegmentationBundle:
        debug_enabled = (
            debug_segmentation_bundles_enabled()
            if allow_debug_bundles is None
            else allow_debug_bundles
        )
        bundle_id = self.active_bundle_id()
        if bundle_id and (debug_enabled or not is_debug_only_bundle_id(bundle_id)):
            try:
                return self.load_bundle(bundle_id)
            except Exception:
                pass
        fallback_bundle_id = self.preferred_production_bundle_id()
        if fallback_bundle_id:
            return self.load_bundle(fallback_bundle_id)
        if bundle_id and is_debug_only_bundle_id(bundle_id) and not debug_enabled:
            raise RuntimeError(
                "The configured segmentation bundle is quarantined for debug-only use. "
                "Activate an nnU-Net production bundle for the normal Analyze path, or "
                f"set {DEBUG_SEGMENTATION_BUNDLES_ENV_VAR}=1 for explicit debug runs."
            )
        raise RuntimeError(
            "No active production segmentation bundle is configured. "
            "Install and activate an nnU-Net bundle with "
            "tools/manage_segmentation_backends.py or tools/install_segmentation_bundle.py."
        )

    def production_status(self) -> tuple[str, str]:
        bundle_id = self.resolved_active_bundle_id()
        if not bundle_id:
            return ("Production (Not Installed)", "danger")
        try:
            bundle = self.load_bundle(bundle_id)
        except Exception:
            return (f"Production (Missing Bundle: {bundle_id})", "danger")
        return (bundle.display_name, "info")


def _resolve_nnunet_trainer_root(source_root: Path) -> Path:
    resolved = source_root.resolve()
    if (resolved / "plans.json").exists() and any(resolved.glob("fold_*")):
        return resolved
    candidates = [
        path
        for path in resolved.rglob("*")
        if path.is_dir() and (path / "plans.json").exists() and any(path.glob("fold_*"))
    ]
    if not candidates:
        raise FileNotFoundError(
            f"Unable to locate an nnU-Net trainer directory under {resolved}."
        )
    if len(candidates) > 1:
        raise ValueError(
            f"Source path {resolved} contains multiple trainer directories; pass one explicitly."
        )
    return candidates[0]


def _detect_checkpoints(
    *,
    bundle_dir: Path,
    trainer_dir: Path,
) -> tuple[SegmentationBundleCheckpoint, ...]:
    checkpoints: list[SegmentationBundleCheckpoint] = []
    for fold_dir in sorted(trainer_dir.glob("fold_*"), key=lambda path: path.name.lower()):
        fold_value = fold_dir.name.removeprefix("fold_")
        for checkpoint_path in sorted(
            fold_dir.glob("checkpoint*.pth"),
            key=lambda path: (_CHECKPOINT_PRIORITY.get(path.name, 99), path.name.lower()),
        ):
            checkpoint_name = checkpoint_path.name
            checkpoint_id = f"fold-{fold_value}:{checkpoint_name.removesuffix('.pth')}"
            checkpoints.append(
                SegmentationBundleCheckpoint(
                    checkpoint_id=checkpoint_id,
                    fold=fold_value,
                    checkpoint_name=checkpoint_name,
                    relative_path=str(checkpoint_path.relative_to(bundle_dir)),
                )
            )
    if not checkpoints:
        raise FileNotFoundError(f"No nnU-Net checkpoints found under {trainer_dir}.")
    return tuple(checkpoints)


def _default_active_checkpoint_id(
    checkpoints: tuple[SegmentationBundleCheckpoint, ...],
) -> str:
    def checkpoint_sort_key(
        checkpoint: SegmentationBundleCheckpoint,
    ) -> tuple[int, int, str]:
        try:
            fold_index = int(checkpoint.fold)
        except ValueError:
            fold_index = 999
        priority = _CHECKPOINT_PRIORITY.get(checkpoint.checkpoint_name, 99)
        return (priority, fold_index, checkpoint.checkpoint_id)

    return min(checkpoints, key=checkpoint_sort_key).checkpoint_id


def _resolve_active_checkpoint_id(
    checkpoints: tuple[SegmentationBundleCheckpoint, ...],
    active_checkpoint_id: str | None,
) -> str:
    available_checkpoint_ids = {checkpoint.checkpoint_id for checkpoint in checkpoints}
    if active_checkpoint_id is not None:
        resolved_checkpoint_id = str(active_checkpoint_id).strip()
        if resolved_checkpoint_id not in available_checkpoint_ids:
            available = ", ".join(sorted(available_checkpoint_ids))
            raise ValueError(
                "Unknown active_checkpoint_id for segmentation bundle install: "
                f"{resolved_checkpoint_id!r}. Available checkpoints: {available}"
            )
        return resolved_checkpoint_id
    distinct_folds = {checkpoint.fold for checkpoint in checkpoints}
    if len(distinct_folds) > 1:
        available = ", ".join(sorted(available_checkpoint_ids))
        raise ValueError(
            "The source nnU-Net trainer tree exposes multiple folds. "
            "Pass active_checkpoint_id explicitly when installing the production bundle. "
            f"Available checkpoints: {available}"
        )
    return _default_active_checkpoint_id(checkpoints)


def _resolve_fold_checkpoint_id(
    *,
    source_results_root: Path,
    fold: str,
) -> str:
    trainer_root = _resolve_nnunet_trainer_root(source_results_root)
    fold_dir = trainer_root / f"fold_{fold}"
    if not fold_dir.exists():
        raise FileNotFoundError(f"Unable to locate fold_{fold} under {trainer_root}.")
    checkpoint_paths = sorted(
        fold_dir.glob("checkpoint*.pth"),
        key=lambda path: (_CHECKPOINT_PRIORITY.get(path.name, 99), path.name.lower()),
    )
    if not checkpoint_paths:
        raise FileNotFoundError(f"No nnU-Net checkpoints found under {fold_dir}.")
    checkpoint_name = checkpoint_paths[0].name.removesuffix(".pth")
    return f"fold-{fold}:{checkpoint_name}"


def known_segmentation_backend(backend_id: str) -> KnownSegmentationBackend:
    normalized_backend_id = _normalize_bundle_id(backend_id)
    for backend in KNOWN_SEGMENTATION_BACKENDS:
        if backend.backend_id == normalized_backend_id:
            return backend
    available = ", ".join(item.backend_id for item in KNOWN_SEGMENTATION_BACKENDS)
    raise ValueError(
        f"Unknown segmentation backend {backend_id!r}. Available backends: {available}"
    )


def identify_known_backend_id(
    bundle: InstalledSegmentationBundle,
) -> str | None:
    canonical_bundle_id = _canonical_backend_id(bundle.bundle_id)
    if canonical_bundle_id is not None:
        return canonical_bundle_id

    if (
        bundle.driver_id != DEFAULT_NNUNET_DRIVER_ID
        or bundle.family != DEFAULT_NNUNET_FAMILY
    ):
        return None

    fold_tokens = " ".join(
        (
            bundle.bundle_id.lower(),
            bundle.display_name.lower(),
            bundle.active_checkpoint_id.lower(),
        )
    )
    if re.search(r"\bfold(?:[-\s]?0)\b", fold_tokens):
        return DEFAULT_FOLD0_BUNDLE_ID
    if re.search(r"\bfold(?:[-\s]?1)\b", fold_tokens):
        return DEFAULT_FOLD1_BUNDLE_ID
    return None


def map_installed_bundles_to_known_backends(
    bundles: Iterable[InstalledSegmentationBundle],
) -> dict[str, InstalledSegmentationBundle]:
    mapped: dict[str, InstalledSegmentationBundle] = {}
    for bundle in bundles:
        backend_id = identify_known_backend_id(bundle)
        if backend_id is None:
            continue
        current = mapped.get(backend_id)
        if current is None or (
            current.bundle_id != backend_id and bundle.bundle_id == backend_id
        ):
            mapped[backend_id] = bundle
    return mapped


def build_legacy_nnunet_runtime_model(
    *,
    results_root: Path,
    dataset_id: int,
    dataset_name: str,
    trainer_name: str,
    plan_name: str,
    configuration: str,
    fold: str,
    checkpoint_name: str,
    display_name: str = DEFAULT_DISPLAY_NAME,
    family: str = DEFAULT_NNUNET_FAMILY,
    environment_id: str = DEFAULT_NNUNET_ENVIRONMENT_ID,
    driver_id: str = DEFAULT_NNUNET_DRIVER_ID,
    label_mapping: dict[str, int] | None = None,
) -> SegmentationRuntimeModel:
    runtime_results_root = results_root.resolve()
    dataset_dir = runtime_results_root / f"Dataset{dataset_id:03d}_{dataset_name}"
    trainer_dir = dataset_dir / f"{trainer_name}__{plan_name}__{configuration}"
    checkpoint_path = trainer_dir / f"fold_{fold}" / checkpoint_name
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Missing nnU-Net checkpoint for inference: {checkpoint_path}")
    checkpoint_id = f"fold-{fold}:{checkpoint_name.removesuffix('.pth')}"
    return SegmentationRuntimeModel(
        model_id=f"legacy-{dataset_id:03d}-{trainer_name}-{plan_name}-{configuration}",
        display_name=display_name,
        family=family,
        driver_id=driver_id,
        environment_id=environment_id,
        modality=DEFAULT_BUNDLE_MODALITY,
        inference_spec=SegmentationBundleInferenceSpec(
            dataset_id=dataset_id,
            dataset_name=dataset_name,
            trainer_name=trainer_name,
            plan_name=plan_name,
            configuration=configuration,
        ),
        checkpoint=SegmentationBundleCheckpoint(
            checkpoint_id=checkpoint_id,
            fold=str(fold),
            checkpoint_name=checkpoint_name,
            relative_path=str(checkpoint_path.relative_to(runtime_results_root)),
        ),
        runtime_results_root=runtime_results_root,
        checkpoint_path=checkpoint_path,
        label_mapping=dict(label_mapping or DEFAULT_LABEL_MAPPING),
        provenance={
            "source": "legacy-results-root",
            "source_results_root": str(runtime_results_root),
        },
    )


def install_nnunet_bundle(
    *,
    store: CaseStore,
    source_results_root: Path,
    bundle_id: str,
    active_checkpoint_id: str | None = None,
    display_name: str = DEFAULT_DISPLAY_NAME,
    activate: bool = False,
    settings: SettingsService | None = None,
    family: str = DEFAULT_NNUNET_FAMILY,
    environment_id: str = DEFAULT_NNUNET_ENVIRONMENT_ID,
    driver_id: str = DEFAULT_NNUNET_DRIVER_ID,
    modality: str = DEFAULT_BUNDLE_MODALITY,
    runtime_root: str = DEFAULT_NNUNET_RUNTIME_ROOT,
) -> InstalledSegmentationBundle:
    sanitized_bundle_id = _normalize_bundle_id(bundle_id)
    if not sanitized_bundle_id:
        raise ValueError("Bundle id must contain at least one alphanumeric character.")

    registry = SegmentationBundleRegistry(store, settings=settings)
    registry.ensure_root()

    source_trainer_root = _resolve_nnunet_trainer_root(source_results_root)
    dataset_dir = source_trainer_root.parent
    if not dataset_dir.name.startswith("Dataset"):
        raise ValueError(
            f"Trainer root must live under a Dataset### directory. Got: {source_trainer_root}"
        )

    target_bundle_dir = registry.bundle_dir(sanitized_bundle_id)
    if target_bundle_dir.exists():
        raise FileExistsError(f"Segmentation bundle already exists: {sanitized_bundle_id}")

    target_runtime_root = (
        target_bundle_dir / runtime_root / dataset_dir.name / source_trainer_root.name
    )
    shutil.copytree(
        source_trainer_root,
        target_runtime_root,
        copy_function=_copy_file_or_hardlink,
    )
    (target_bundle_dir / DEFAULT_NNUNET_RAW_ROOT).mkdir(parents=True, exist_ok=True)
    (target_bundle_dir / DEFAULT_NNUNET_PREPROCESSED_ROOT).mkdir(
        parents=True,
        exist_ok=True,
    )

    checkpoints = _detect_checkpoints(bundle_dir=target_bundle_dir, trainer_dir=target_runtime_root)
    inference_spec = SegmentationBundleInferenceSpec(
        dataset_id=int(dataset_dir.name[7:10]),
        dataset_name=dataset_dir.name.split("_", 1)[1],
        trainer_name=source_trainer_root.name.split("__", 1)[0],
        plan_name=source_trainer_root.name.split("__", 2)[1],
        configuration=source_trainer_root.name.rsplit("__", 1)[1],
    )
    bundle = InstalledSegmentationBundle(
        bundle_id=sanitized_bundle_id,
        family=family,
        display_name=display_name,
        environment_id=environment_id,
        driver_id=driver_id,
        modality=modality,
        inference_spec=inference_spec,
        checkpoints=checkpoints,
        active_checkpoint_id=_resolve_active_checkpoint_id(checkpoints, active_checkpoint_id),
        label_mapping=dict(DEFAULT_LABEL_MAPPING),
        provenance={
            "installed_at_utc": utc_now(),
            "source_results_root": str(source_trainer_root.resolve()),
            "installer": "tools/install_segmentation_bundle.py",
        },
        runtime_root=runtime_root,
        bundle_dir=target_bundle_dir,
    )
    target_bundle_dir.mkdir(parents=True, exist_ok=True)
    bundle.manifest_path.write_text(json.dumps(bundle.to_dict(), indent=2), encoding="utf-8")

    if activate:
        registry.set_active_bundle_id(bundle.bundle_id)

    return bundle


def install_known_segmentation_backend(
    *,
    store: CaseStore,
    backend_id: str,
    activate: bool = False,
    settings: SettingsService | None = None,
    source_results_root: Path = DEFAULT_LEGACY_TRAINER_ROOT,
) -> InstalledSegmentationBundle:
    backend = known_segmentation_backend(backend_id)
    if backend.backend_id == DEFAULT_FOLD0_BUNDLE_ID:
        return install_nnunet_bundle(
            store=store,
            source_results_root=source_results_root,
            bundle_id=backend.backend_id,
            active_checkpoint_id=_resolve_fold_checkpoint_id(
                source_results_root=source_results_root,
                fold="0",
            ),
            display_name=backend.display_name,
            activate=activate,
            settings=settings,
            family=backend.family,
            environment_id=backend.environment_id,
            driver_id=backend.driver_id,
            modality=backend.modality,
        )
    if backend.backend_id == DEFAULT_FOLD1_BUNDLE_ID:
        return install_nnunet_bundle(
            store=store,
            source_results_root=source_results_root,
            bundle_id=backend.backend_id,
            active_checkpoint_id=_resolve_fold_checkpoint_id(
                source_results_root=source_results_root,
                fold="1",
            ),
            display_name=backend.display_name,
            activate=activate,
            settings=settings,
            family=backend.family,
            environment_id=backend.environment_id,
            driver_id=backend.driver_id,
            modality=backend.modality,
        )
    raise ValueError(f"Unsupported segmentation backend installer: {backend.backend_id}")
