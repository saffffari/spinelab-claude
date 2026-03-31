from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from spinelab.segmentation_profiles import (
    DEFAULT_SEGMENTATION_PROFILE,
    canonical_segmentation_profile,
)

CURRENT_SCHEMA_VERSION = 5


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def make_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10]}"


def _coerce_bool(payload: Any, *, default: bool = False) -> bool:
    if isinstance(payload, bool):
        return payload
    if isinstance(payload, str):
        normalized = payload.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    if isinstance(payload, (int, float)):
        return bool(payload)
    return default


def _coerce_str_dict(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    normalized: dict[str, str] = {}
    for key, value in payload.items():
        normalized[str(key)] = str(value)
    return normalized


def _coerce_float_dict(payload: Any) -> dict[str, float]:
    if not isinstance(payload, dict):
        return {}
    normalized: dict[str, float] = {}
    for key, value in payload.items():
        try:
            normalized[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return normalized


def _coerce_str_list(payload: Any) -> list[str]:
    if not isinstance(payload, list):
        return []
    return [str(item) for item in payload]


def _coerce_int_tuple(payload: Any, size: int) -> tuple[int, ...] | None:
    if not isinstance(payload, (list, tuple)) or len(payload) != size:
        return None
    try:
        return tuple(int(item) for item in payload)
    except (TypeError, ValueError):
        return None


def _coerce_float_tuple(payload: Any, size: int) -> tuple[float, ...] | None:
    if not isinstance(payload, (list, tuple)) or len(payload) != size:
        return None
    try:
        return tuple(float(item) for item in payload)
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class StudyAsset:
    asset_id: str
    kind: str
    label: str
    source_path: str
    managed_path: str
    status: str = "ready"
    processing_role: str | None = None
    created_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class PipelineRun:
    stage: str
    status: str
    run_id: str = field(default_factory=lambda: make_id("run"))
    backend_tool: str = "internal"
    environment_id: str = "app"
    device: str = "cpu"
    requested_device: str = "auto"
    effective_device: str = "cpu"
    cuda_version: str | None = None
    gpu_name: str | None = None
    total_vram_mb: int | None = None
    backend_health: dict[str, str] = field(default_factory=dict)
    performance_trace_path: str | None = None
    timings: dict[str, float] = field(default_factory=dict)
    tool_version: str | None = None
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    fallback_reason: str | None = None
    stage_version: str = "0.1.0"
    message: str = ""
    started_at: str = field(default_factory=utc_now)
    finished_at: str | None = None
    error_text: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PipelineRun:
        return cls(
            stage=str(payload.get("stage", "")),
            status=str(payload.get("status", "")),
            run_id=str(payload.get("run_id", make_id("run"))),
            backend_tool=str(payload.get("backend_tool", "internal")),
            environment_id=str(payload.get("environment_id", "app")),
            device=str(
                payload.get(
                    "device",
                    payload.get("effective_device", "cpu"),
                )
            ),
            requested_device=str(
                payload.get(
                    "requested_device",
                    payload.get("device", "auto"),
                )
            ),
            effective_device=str(
                payload.get(
                    "effective_device",
                    payload.get("device", "cpu"),
                )
            ),
            cuda_version=(
                str(payload["cuda_version"]) if payload.get("cuda_version") is not None else None
            ),
            gpu_name=str(payload["gpu_name"]) if payload.get("gpu_name") is not None else None,
            total_vram_mb=(
                int(payload["total_vram_mb"])
                if payload.get("total_vram_mb") is not None
                else None
            ),
            backend_health=_coerce_str_dict(payload.get("backend_health")),
            performance_trace_path=(
                str(payload["performance_trace_path"])
                if payload.get("performance_trace_path") is not None
                else None
            ),
            timings=_coerce_float_dict(payload.get("timings")),
            tool_version=(
                str(payload["tool_version"]) if payload.get("tool_version") is not None else None
            ),
            inputs=_coerce_str_list(payload.get("inputs")),
            outputs=_coerce_str_list(payload.get("outputs")),
            fallback_reason=(
                str(payload["fallback_reason"])
                if payload.get("fallback_reason") is not None
                else None
            ),
            stage_version=str(payload.get("stage_version", "0.1.0")),
            message=str(payload.get("message", "")),
            started_at=str(payload.get("started_at", utc_now())),
            finished_at=(
                str(payload["finished_at"]) if payload.get("finished_at") is not None else None
            ),
            error_text=(
                str(payload["error_text"]) if payload.get("error_text") is not None else None
            ),
        )


@dataclass(slots=True)
class PipelineArtifact:
    artifact_id: str
    kind: str
    label: str
    path: str
    stage: str
    artifact_type: str = ""
    schema_version: str = "spinelab.v1"
    coordinate_frame: str = ""
    review_surface: str = ""
    status: str = "complete"
    summary: str = ""
    asset_id: str | None = None
    source_artifact_ids: list[str] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PipelineArtifact:
        return cls(
            artifact_id=str(payload.get("artifact_id", make_id("artifact"))),
            kind=str(payload.get("kind", "")),
            label=str(payload.get("label", "")),
            path=str(payload.get("path", "")),
            stage=str(payload.get("stage", "")),
            artifact_type=str(payload.get("artifact_type", payload.get("kind", ""))),
            schema_version=str(payload.get("schema_version", "spinelab.v1")),
            coordinate_frame=str(payload.get("coordinate_frame", "")),
            review_surface=str(payload.get("review_surface", "")),
            status=str(payload.get("status", "complete")),
            summary=str(payload.get("summary", "")),
            asset_id=str(payload["asset_id"]) if payload.get("asset_id") is not None else None,
            source_artifact_ids=_coerce_str_list(payload.get("source_artifact_ids")),
            metadata=_coerce_str_dict(payload.get("metadata")),
            created_at=str(payload.get("created_at", utc_now())),
        )


@dataclass(slots=True)
class MetricRecord:
    metric_id: str
    key: str
    label: str
    value_text: str
    value: float | None = None
    unit: str = ""
    provenance: str = "pipeline"
    source_stage: str = "measurements"
    definition_version: str = "measurement-spec.v1"
    measurement_mode: str = "native_3d"
    coordinate_frame: str = "patient-body"
    valid: bool = True
    invalid_reason: str = ""
    uncertainty_text: str = ""
    confidence: float | None = None
    source_artifact_ids: list[str] = field(default_factory=list)
    required_primitives: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> MetricRecord:
        raw_value = payload.get("value")
        raw_confidence = payload.get("confidence")
        return cls(
            metric_id=str(payload.get("metric_id", make_id("metric"))),
            key=str(payload.get("key", "")),
            label=str(payload.get("label", "")),
            value_text=str(payload.get("value_text", "")),
            value=float(raw_value) if raw_value is not None else None,
            unit=str(payload.get("unit", "")),
            provenance=str(payload.get("provenance", "pipeline")),
            source_stage=str(payload.get("source_stage", "measurements")),
            definition_version=str(payload.get("definition_version", "measurement-spec.v1")),
            measurement_mode=str(payload.get("measurement_mode", "native_3d")),
            coordinate_frame=str(payload.get("coordinate_frame", "patient-body")),
            valid=_coerce_bool(payload.get("valid"), default=True),
            invalid_reason=str(payload.get("invalid_reason", "")),
            uncertainty_text=str(payload.get("uncertainty_text", "")),
            confidence=float(raw_confidence) if raw_confidence is not None else None,
            source_artifact_ids=_coerce_str_list(payload.get("source_artifact_ids")),
            required_primitives=_coerce_str_list(payload.get("required_primitives")),
            created_at=str(payload.get("created_at", utc_now())),
        )


@dataclass(slots=True)
class FindingRecord:
    finding_id: str
    severity: str
    diagnosis_title: str
    reasoning: str
    vertebra_pair: str = ""
    plane: str | None = None
    source_metric_keys: list[str] = field(default_factory=list)
    review_state: str = "pending"
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> FindingRecord:
        return cls(
            finding_id=str(payload.get("finding_id", make_id("finding"))),
            severity=str(payload.get("severity", "normal")),
            diagnosis_title=str(payload.get("diagnosis_title", "")),
            reasoning=str(payload.get("reasoning", "")),
            vertebra_pair=str(payload.get("vertebra_pair", "")),
            plane=str(payload["plane"]) if payload.get("plane") is not None else None,
            source_metric_keys=_coerce_str_list(payload.get("source_metric_keys")),
            review_state=str(payload.get("review_state", "pending")),
            created_at=str(payload.get("created_at", utc_now())),
        )


@dataclass(slots=True)
class ReviewDecision:
    finding_id: str
    status: str
    reviewer_name: str = ""
    reviewer_license: str = ""
    notes: str = ""
    decided_at: str = field(default_factory=utc_now)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ReviewDecision:
        return cls(
            finding_id=str(payload.get("finding_id", "")),
            status=str(payload.get("status", "")),
            reviewer_name=str(payload.get("reviewer_name", "")),
            reviewer_license=str(payload.get("reviewer_license", "")),
            notes=str(payload.get("notes", "")),
            decided_at=str(payload.get("decided_at", utc_now())),
        )


@dataclass(slots=True)
class VolumeMetadata:
    volume_id: str
    modality: str
    source_path: str
    canonical_path: str
    dimensions: tuple[int, int, int]
    asset_id: str | None = None
    voxel_spacing: tuple[float, float, float] | None = None
    orientation: str = ""
    value_range: tuple[float, float] | None = None
    intensity_unit: str = ""
    source_coordinate_frame: str = "native-image"
    coordinate_frame: str = "normalized-volume"
    native_to_canonical_transform: dict[str, str] = field(default_factory=dict)
    qc_summary: str = ""
    provenance: str = "pipeline"
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> VolumeMetadata:
        dimensions = cast(
            tuple[int, int, int],
            _coerce_int_tuple(payload.get("dimensions"), 3) or (0, 0, 0),
        )
        voxel_spacing = _coerce_float_tuple(payload.get("voxel_spacing"), 3)
        value_range = _coerce_float_tuple(payload.get("value_range"), 2)
        return cls(
            volume_id=str(payload.get("volume_id", make_id("volume"))),
            modality=str(payload.get("modality", "")),
            source_path=str(payload.get("source_path", "")),
            canonical_path=str(payload.get("canonical_path", "")),
            dimensions=dimensions,
            asset_id=str(payload["asset_id"]) if payload.get("asset_id") is not None else None,
            voxel_spacing=cast(tuple[float, float, float] | None, voxel_spacing),
            orientation=str(payload.get("orientation", "")),
            value_range=cast(tuple[float, float] | None, value_range),
            intensity_unit=str(payload.get("intensity_unit", "")),
            source_coordinate_frame=str(payload.get("source_coordinate_frame", "native-image")),
            coordinate_frame=str(payload.get("coordinate_frame", "normalized-volume")),
            native_to_canonical_transform=_coerce_str_dict(
                payload.get("native_to_canonical_transform")
            ),
            qc_summary=str(payload.get("qc_summary", "")),
            provenance=str(payload.get("provenance", "pipeline")),
            created_at=str(payload.get("created_at", utc_now())),
        )


@dataclass(slots=True)
class MeasurementSet:
    values: dict[str, str] = field(default_factory=dict)
    records: list[MetricRecord] = field(default_factory=list)
    reviewed: bool = False
    provenance: str = "mock"
    definition_version: str = "measurement-spec.v1"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> MeasurementSet:
        values = _coerce_str_dict(payload.get("values"))
        records = [MetricRecord.from_dict(item) for item in payload.get("records", [])]
        if not values and records:
            values = {
                (record.label or record.key): record.value_text
                for record in records
                if record.value_text
            }
        return cls(
            values=values,
            records=records,
            reviewed=_coerce_bool(payload.get("reviewed"), default=False),
            provenance=str(payload.get("provenance", "mock")),
            definition_version=str(payload.get("definition_version", "measurement-spec.v1")),
        )

    @classmethod
    def demo_targets(cls) -> MeasurementSet:
        records = [
            MetricRecord(
                metric_id="demo-cobb-angle",
                key="cobb_angle",
                label="Cobb Angle",
                value_text="42.0 deg",
                value=42.0,
                unit="deg",
                provenance="demo_targets",
                source_stage="measurement_targets",
            ),
            MetricRecord(
                metric_id="demo-thoracic-kyphosis",
                key="thoracic_kyphosis",
                label="Thoracic Kyphosis",
                value_text="34.6 deg",
                value=34.6,
                unit="deg",
                provenance="demo_targets",
                source_stage="measurement_targets",
            ),
            MetricRecord(
                metric_id="demo-lumbar-lordosis",
                key="lumbar_lordosis",
                label="Lumbar Lordosis",
                value_text="46.2 deg",
                value=46.2,
                unit="deg",
                provenance="demo_targets",
                source_stage="measurement_targets",
            ),
            MetricRecord(
                metric_id="demo-pelvic-tilt",
                key="pelvic_tilt",
                label="Pelvic Tilt",
                value_text="12.1 deg",
                value=12.1,
                unit="deg",
                provenance="demo_targets",
                source_stage="measurement_targets",
            ),
            MetricRecord(
                metric_id="demo-sva",
                key="sagittal_vertical_axis",
                label="Sagittal Vertical Axis",
                value_text="23.0 mm",
                value=23.0,
                unit="mm",
                provenance="demo_targets",
                source_stage="measurement_targets",
            ),
        ]
        return cls(
            values={record.label: record.value_text for record in records},
            records=records,
            reviewed=False,
            provenance="demo_targets",
        )


@dataclass(slots=True)
class CaseManifest:
    case_id: str
    patient_name: str
    schema_version: int = CURRENT_SCHEMA_VERSION
    patient_id: str = ""
    age_text: str = ""
    sex: str = ""
    diagnosis: str = ""
    cobb_angle: str = ""
    analysis_pose_mode: str = ""
    comparison_modalities: dict[str, str] = field(default_factory=dict)
    segmentation_profile: str = DEFAULT_SEGMENTATION_PROFILE
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    assets: list[StudyAsset] = field(default_factory=list)
    procedure_history: list[str] = field(default_factory=list)
    pipeline_runs: list[PipelineRun] = field(default_factory=list)
    measurements: MeasurementSet = field(default_factory=MeasurementSet)
    artifacts: list[PipelineArtifact] = field(default_factory=list)
    findings: list[FindingRecord] = field(default_factory=list)
    review_decisions: list[ReviewDecision] = field(default_factory=list)
    volumes: list[VolumeMetadata] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> CaseManifest:
        return cls(
            case_id=payload["case_id"],
            patient_name=payload.get("patient_name", ""),
            schema_version=int(payload.get("schema_version", 1)),
            patient_id=payload.get("patient_id", ""),
            age_text=payload.get("age_text", ""),
            sex=payload.get("sex", ""),
            diagnosis=payload.get("diagnosis", ""),
            cobb_angle=payload.get("cobb_angle", ""),
            analysis_pose_mode=str(payload.get("analysis_pose_mode", "")),
            comparison_modalities=_coerce_str_dict(payload.get("comparison_modalities")),
            segmentation_profile=canonical_segmentation_profile(
                payload.get("segmentation_profile")
            ),
            created_at=payload.get("created_at", utc_now()),
            updated_at=payload.get("updated_at", utc_now()),
            assets=[StudyAsset(**item) for item in payload.get("assets", [])],
            procedure_history=_coerce_str_list(payload.get("procedure_history")),
            pipeline_runs=[
                PipelineRun.from_dict(item) for item in payload.get("pipeline_runs", [])
            ],
            measurements=MeasurementSet.from_dict(payload.get("measurements", {})),
            artifacts=[PipelineArtifact.from_dict(item) for item in payload.get("artifacts", [])],
            findings=[FindingRecord.from_dict(item) for item in payload.get("findings", [])],
            review_decisions=[
                ReviewDecision.from_dict(item) for item in payload.get("review_decisions", [])
            ],
            volumes=[VolumeMetadata.from_dict(item) for item in payload.get("volumes", [])],
        )

    def get_asset(self, asset_id: str) -> StudyAsset | None:
        for asset in self.assets:
            if asset.asset_id == asset_id:
                return asset
        return None

    def get_asset_for_role(self, role: str) -> StudyAsset | None:
        for asset in self.assets:
            if asset.processing_role == role:
                return asset
        return None

    def get_volume(self, asset_id: str) -> VolumeMetadata | None:
        for volume in self.volumes:
            if volume.asset_id == asset_id:
                return volume
        return None

    def assign_asset_to_role(self, asset_id: str, role: str) -> StudyAsset | None:
        asset = self.get_asset(asset_id)
        if asset is None:
            return None
        for candidate in self.assets:
            if candidate.processing_role == role and candidate.asset_id != asset_id:
                candidate.processing_role = None
        asset.processing_role = role
        return asset

    @classmethod
    def blank(cls) -> CaseManifest:
        return cls(
            case_id=f"case-{uuid4().hex[:8]}",
            patient_name="",
            measurements=MeasurementSet(values={}, reviewed=False, provenance="pending"),
        )

    @classmethod
    def demo(cls) -> CaseManifest:
        return cls(
            case_id="case-sarah-johnson",
            patient_name="Sarah Johnson",
            patient_id="P001",
            age_text="16 years",
            sex="F",
            diagnosis="Adolescent Idiopathic Scoliosis",
            cobb_angle="42.0 deg",
            procedure_history=[
                "Posterior Spinal Fusion",
                "Pre-operative Assessment",
                "Initial Consultation",
            ],
            assets=[],
            pipeline_runs=[
                PipelineRun(stage="segmentation", status="complete", outputs=["vertebra_meshes"]),
                PipelineRun(stage="registration", status="processing", outputs=[]),
            ],
            measurements=MeasurementSet.demo_targets(),
        )
