from __future__ import annotations

from dataclasses import asdict
from typing import Any

from spinelab.ai.pointcloud.geometry import (
    compute_disc_heights,
    compute_listhesis,
    compute_lumbar_lordosis,
    compute_segmental_lordosis,
    compute_thoracic_kyphosis,
)
from spinelab.io import CaseStore
from spinelab.models import CaseManifest, MetricRecord, PipelineArtifact
from spinelab.models.manifest import make_id
from spinelab.ontology import (
    STANDARD_LEVEL_IDS,
    GlobalStructureId,
    PrimitiveId,
)
from spinelab.pipeline.artifacts import measurement_summary_path, write_json_artifact
from spinelab.pipeline.contracts import PipelineStageName, StageExecutionResult
from spinelab.pipeline.stages.common import artifact_for_type, read_json_payload

_MEASUREMENT_MODE = "single_pose_native_3d"
_MEASUREMENT_COORDINATE_FRAME = "patient-body-supine"


def _vertebra_lookup(payload: dict[str, Any], key: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for entry in payload.get(key, []):
        if not isinstance(entry, dict):
            continue
        vertebra_id = str(entry.get("vertebra_id", "")).upper()
        if vertebra_id:
            result[vertebra_id] = entry
    return result


def _primitive_ref(level_id: str, primitive_id: PrimitiveId) -> str:
    return f"{level_id}.{primitive_id.value}"


def _global_ref(structure_id: GlobalStructureId) -> str:
    return structure_id.value


def _metric_record(
    *,
    key: str,
    label: str,
    value: float | None,
    unit: str,
    valid: bool,
    invalid_reason: str,
    uncertainty_text: str,
    source_artifact_ids: list[str],
    required_primitives: list[str],
) -> MetricRecord:
    value_text = f"{value:.1f} {unit}" if valid and value is not None else "Unavailable"
    return MetricRecord(
        metric_id=make_id("metric"),
        key=key,
        label=label,
        value_text=value_text,
        value=value if valid else None,
        unit=unit if valid else "",
        provenance="artifact-backed",
        source_stage=PipelineStageName.MEASUREMENTS.value,
        definition_version="measurement-spec.v1",
        measurement_mode=_MEASUREMENT_MODE,
        coordinate_frame=_MEASUREMENT_COORDINATE_FRAME,
        valid=valid,
        invalid_reason=invalid_reason,
        uncertainty_text=uncertainty_text,
        confidence=0.84 if valid else None,
        source_artifact_ids=source_artifact_ids,
        required_primitives=required_primitives,
    )


def _supports_measurements(entry: dict[str, Any]) -> bool:
    return bool(entry.get("supports_standard_measurements", True))


def _primitives_for_level(
    lookup: dict[str, dict[str, Any]],
    level_id: str,
) -> dict[str, Any]:
    return dict(lookup[level_id]["primitives"])


def _segment_slug(cranial_level: str, caudal_level: str) -> str:
    return f"{cranial_level.lower()}_{caudal_level.lower()}"


def _append_single_pose_global_metrics(
    metrics: list[MetricRecord],
    *,
    landmark_lookup: dict[str, dict[str, Any]],
    source_artifact_ids: list[str],
) -> None:
    try:
        lumbar_lordosis = compute_lumbar_lordosis(
            _primitives_for_level(landmark_lookup, "L1"),
            _primitives_for_level(landmark_lookup, "S1"),
        )
        metrics.append(
            _metric_record(
                key="lumbar_lordosis",
                label="Lumbar Lordosis",
                value=lumbar_lordosis,
                unit="deg",
                valid=True,
                invalid_reason="",
                uncertainty_text=(
                    "Native 3D single-pose angle derived directly from landmark primitives."
                ),
                source_artifact_ids=source_artifact_ids,
                required_primitives=[
                    _primitive_ref("L1", PrimitiveId.SUPERIOR_ENDPLATE_PLANE),
                    _primitive_ref("S1", PrimitiveId.SUPERIOR_ENDPLATE_PLANE),
                ],
            )
        )
    except KeyError:
        metrics.append(
            _metric_record(
                key="lumbar_lordosis",
                label="Lumbar Lordosis",
                value=None,
                unit="deg",
                valid=False,
                invalid_reason="Missing L1 or S1 endplate primitives.",
                uncertainty_text="Not computed.",
                source_artifact_ids=source_artifact_ids,
                required_primitives=[
                    _primitive_ref("L1", PrimitiveId.SUPERIOR_ENDPLATE_PLANE),
                    _primitive_ref("S1", PrimitiveId.SUPERIOR_ENDPLATE_PLANE),
                ],
            )
        )

    try:
        thoracic_kyphosis = compute_thoracic_kyphosis(
            _primitives_for_level(landmark_lookup, "T4"),
            _primitives_for_level(landmark_lookup, "T12"),
        )
        metrics.append(
            _metric_record(
                key="thoracic_kyphosis",
                label="Thoracic Kyphosis",
                value=thoracic_kyphosis,
                unit="deg",
                valid=True,
                invalid_reason="",
                uncertainty_text=(
                    "Native 3D single-pose angle derived directly from landmark primitives."
                ),
                source_artifact_ids=source_artifact_ids,
                required_primitives=[
                    _primitive_ref("T4", PrimitiveId.SUPERIOR_ENDPLATE_PLANE),
                    _primitive_ref("T12", PrimitiveId.INFERIOR_ENDPLATE_PLANE),
                ],
            )
        )
    except KeyError:
        metrics.append(
            _metric_record(
                key="thoracic_kyphosis",
                label="Thoracic Kyphosis",
                value=None,
                unit="deg",
                valid=False,
                invalid_reason="Missing T4 or T12 endplate primitives.",
                uncertainty_text="Not computed.",
                source_artifact_ids=source_artifact_ids,
                required_primitives=[
                    _primitive_ref("T4", PrimitiveId.SUPERIOR_ENDPLATE_PLANE),
                    _primitive_ref("T12", PrimitiveId.INFERIOR_ENDPLATE_PLANE),
                ],
            )
        )

    metrics.extend(
        (
            _metric_record(
                key="cobb_angle",
                label="Cobb Angle",
                value=None,
                unit="deg",
                valid=False,
                invalid_reason=(
                    "Single-pose native 3D analysis does not yet provide a radiograph-equivalent "
                    "coronal Cobb measurement."
                ),
                uncertainty_text="Fail-closed pending projected coronal measurement support.",
                source_artifact_ids=source_artifact_ids,
                required_primitives=[
                    _primitive_ref("T4", PrimitiveId.SUPERIOR_ENDPLATE_PLANE),
                    _primitive_ref("L5", PrimitiveId.INFERIOR_ENDPLATE_PLANE),
                ],
            ),
            _metric_record(
                key="sagittal_vertical_axis",
                label="Sagittal Vertical Axis",
                value=None,
                unit="mm",
                valid=False,
                invalid_reason=(
                    "Single-pose native 3D analysis intentionally excludes radiograph-equivalent "
                    "global balance metrics."
                ),
                uncertainty_text="Fail-closed pending standing/projection-aware balance recovery.",
                source_artifact_ids=source_artifact_ids,
                required_primitives=[
                    _global_ref(GlobalStructureId.C7_CENTROID),
                    _global_ref(GlobalStructureId.POSTERIOR_SUPERIOR_S1_CORNER),
                ],
            ),
            _metric_record(
                key="pelvic_tilt",
                label="Pelvic Tilt",
                value=None,
                unit="deg",
                valid=False,
                invalid_reason=(
                    "Field of view and primitive package do not yet include the bilateral "
                    "femoral head or hip-axis landmarks required for pelvic tilt."
                ),
                uncertainty_text="Fail-closed until pelvic global structures are available.",
                source_artifact_ids=source_artifact_ids,
                required_primitives=[
                    _global_ref(GlobalStructureId.S1_SUPERIOR_MIDPOINT),
                    _global_ref(GlobalStructureId.LEFT_FEMORAL_HEAD_CENTER),
                    _global_ref(GlobalStructureId.RIGHT_FEMORAL_HEAD_CENTER),
                ],
            ),
        )
    )


def _append_single_pose_segment_metrics(
    metrics: list[MetricRecord],
    *,
    landmark_lookup: dict[str, dict[str, Any]],
    source_artifact_ids: list[str],
) -> None:
    for cranial_level, caudal_level in zip(
        STANDARD_LEVEL_IDS,
        STANDARD_LEVEL_IDS[1:],
        strict=False,
    ):
        cranial_entry = landmark_lookup.get(cranial_level)
        caudal_entry = landmark_lookup.get(caudal_level)
        if cranial_entry is None or caudal_entry is None:
            continue
        if not (_supports_measurements(cranial_entry) and _supports_measurements(caudal_entry)):
            continue
        cranial_primitives = _primitives_for_level(landmark_lookup, cranial_level)
        caudal_primitives = _primitives_for_level(landmark_lookup, caudal_level)
        segment_slug = _segment_slug(cranial_level, caudal_level)
        segment_label = f"{cranial_level}-{caudal_level}"

        try:
            disc_heights = compute_disc_heights(cranial_primitives, caudal_primitives)
            for height_key, height_label in (
                ("anterior", "Anterior Disc Height"),
                ("middle", "Middle Disc Height"),
                ("posterior", "Posterior Disc Height"),
                ("midpoint", "Disc Midpoint Height"),
            ):
                metrics.append(
                    _metric_record(
                        key=f"disc_height_{height_key}_{segment_slug}",
                        label=f"{segment_label} {height_label}",
                        value=float(disc_heights[height_key]),
                        unit="mm",
                        valid=True,
                        invalid_reason="",
                        uncertainty_text=(
                            "Native 3D single-pose disc height derived from adjacent endplate "
                            "landmarks."
                        ),
                        source_artifact_ids=source_artifact_ids,
                        required_primitives=[
                            _primitive_ref(cranial_level, PrimitiveId.INFERIOR_ENDPLATE_PLANE),
                            _primitive_ref(caudal_level, PrimitiveId.SUPERIOR_ENDPLATE_PLANE),
                            _primitive_ref(
                                cranial_level,
                                PrimitiveId.ANTERIOR_INFERIOR_CORNER,
                            ),
                            _primitive_ref(
                                cranial_level,
                                PrimitiveId.INFERIOR_ENDPLATE_MIDPOINT,
                            ),
                            _primitive_ref(
                                cranial_level,
                                PrimitiveId.POSTERIOR_INFERIOR_CORNER,
                            ),
                            _primitive_ref(
                                caudal_level,
                                PrimitiveId.ANTERIOR_SUPERIOR_CORNER,
                            ),
                            _primitive_ref(
                                caudal_level,
                                PrimitiveId.SUPERIOR_ENDPLATE_MIDPOINT,
                            ),
                            _primitive_ref(
                                caudal_level,
                                PrimitiveId.POSTERIOR_SUPERIOR_CORNER,
                            ),
                        ],
                    )
                )
        except KeyError:
            continue

        try:
            listhesis = compute_listhesis(cranial_primitives, caudal_primitives)
            metrics.append(
                _metric_record(
                    key=f"listhesis_{segment_slug}",
                    label=f"{segment_label} Listhesis",
                    value=listhesis,
                    unit="mm",
                    valid=True,
                    invalid_reason="",
                    uncertainty_text=(
                        "Native 3D single-pose posterior-wall translation in the segment frame."
                    ),
                    source_artifact_ids=source_artifact_ids,
                    required_primitives=[
                        _primitive_ref(cranial_level, PrimitiveId.POSTERIOR_WALL_LINE),
                        _primitive_ref(caudal_level, PrimitiveId.POSTERIOR_WALL_LINE),
                        _primitive_ref(caudal_level, PrimitiveId.VERTEBRA_LOCAL_FRAME),
                    ],
                )
            )
        except KeyError:
            pass

        try:
            segmental_angle = compute_segmental_lordosis(cranial_primitives, caudal_primitives)
            metrics.append(
                _metric_record(
                    key=f"segmental_lordosis_{segment_slug}",
                    label=f"{segment_label} Segmental Lordosis/Kyphosis",
                    value=segmental_angle,
                    unit="deg",
                    valid=True,
                    invalid_reason="",
                    uncertainty_text=(
                        "Native 3D single-pose segmental angle from adjacent endplate planes."
                    ),
                    source_artifact_ids=source_artifact_ids,
                    required_primitives=[
                        _primitive_ref(cranial_level, PrimitiveId.INFERIOR_ENDPLATE_PLANE),
                        _primitive_ref(caudal_level, PrimitiveId.SUPERIOR_ENDPLATE_PLANE),
                    ],
                )
            )
        except KeyError:
            pass


def run_measurements_stage(store: CaseStore, manifest: CaseManifest) -> StageExecutionResult:
    landmarks_artifact = artifact_for_type(manifest, "landmarks")
    if landmarks_artifact is None:
        raise ValueError("Measurements require a landmarks artifact.")

    landmarks_payload = read_json_payload(manifest, "landmarks") or {}
    landmark_lookup = _vertebra_lookup(landmarks_payload, "vertebrae")
    if not landmark_lookup:
        raise ValueError("Measurements require landmark primitives for at least one vertebra.")

    metrics: list[MetricRecord] = []
    source_artifact_ids = [landmarks_artifact.artifact_id]
    _append_single_pose_global_metrics(
        metrics,
        landmark_lookup=landmark_lookup,
        source_artifact_ids=source_artifact_ids,
    )
    _append_single_pose_segment_metrics(
        metrics,
        landmark_lookup=landmark_lookup,
        source_artifact_ids=source_artifact_ids,
    )

    summary_path = measurement_summary_path(store, manifest)
    write_json_artifact(
        summary_path,
        {
            "case_id": manifest.case_id,
            "definition_version": "measurement-spec.v1",
            "measurement_mode": _MEASUREMENT_MODE,
            "coordinate_frame": _MEASUREMENT_COORDINATE_FRAME,
            "metrics": [asdict(record) for record in metrics],
            "gui_review_surface": "measurement",
        },
    )
    artifact = PipelineArtifact(
        artifact_id=make_id("artifact"),
        kind="json",
        label="3D Measurements",
        path=str(summary_path),
        stage=PipelineStageName.MEASUREMENTS.value,
        artifact_type="measurements",
        coordinate_frame=_MEASUREMENT_COORDINATE_FRAME,
        review_surface="measurement",
        summary=(
            "Single-pose native 3D measurements derived directly from landmark primitives."
        ),
        source_artifact_ids=source_artifact_ids,
        metadata={
            "definition_version": "measurement-spec.v1",
            "measurement_mode": _MEASUREMENT_MODE,
            "metric_count": str(len(metrics)),
        },
    )
    return StageExecutionResult(
        stage=PipelineStageName.MEASUREMENTS,
        message=(
            "Computed single-pose native 3D measurements from landmark-derived geometry."
        ),
        outputs=[str(summary_path)],
        artifacts=[artifact],
        metrics=metrics,
    )
