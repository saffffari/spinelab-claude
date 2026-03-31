from __future__ import annotations

from collections import deque

from spinelab.pipeline.contracts import PipelineStageName, PipelineStageSpec
from spinelab.pipeline.stages import (
    run_findings_stage,
    run_ingest_stage,
    run_landmarks_stage,
    run_measurements_stage,
    run_mesh_stage,
    run_normalize_stage,
    run_registration_stage,
    run_segmentation_stage,
)

DEFAULT_ANALYSIS_SEQUENCE = (
    PipelineStageName.INGEST,
    PipelineStageName.NORMALIZE,
    PipelineStageName.SEGMENTATION,
    PipelineStageName.MESH,
    PipelineStageName.LANDMARKS,
    PipelineStageName.REGISTRATION,
    PipelineStageName.MEASUREMENTS,
    PipelineStageName.FINDINGS,
)

STAGE_SPECS: dict[PipelineStageName, PipelineStageSpec] = {
    PipelineStageName.INGEST: PipelineStageSpec(
        stage=PipelineStageName.INGEST,
        runner=run_ingest_stage,
        review_surface="import",
        produced_artifact_types=("ingest-summary",),
        description="Capture assigned source assets for GUI Analyze.",
    ),
    PipelineStageName.NORMALIZE: PipelineStageSpec(
        stage=PipelineStageName.NORMALIZE,
        runner=run_normalize_stage,
        dependencies=(PipelineStageName.INGEST,),
        review_surface="import",
        produced_artifact_types=("normalized-volume",),
        description="Prepare canonical review volumes and transform bookkeeping.",
    ),
    PipelineStageName.SEGMENTATION: PipelineStageSpec(
        stage=PipelineStageName.SEGMENTATION,
        runner=run_segmentation_stage,
        dependencies=(PipelineStageName.NORMALIZE,),
        review_surface="import",
        backend_tool="nnunetv2",
        environment_id="nnunet-verse20-win",
        produced_artifact_types=(
            "segmentation",
            "segmentation-label-map",
            "segmentation-run-manifest",
        ),
        description=(
            "Generate per-vertebra labels using the configured production "
            "segmentation backend."
        ),
    ),
    PipelineStageName.MESH: PipelineStageSpec(
        stage=PipelineStageName.MESH,
        runner=run_mesh_stage,
        dependencies=(PipelineStageName.SEGMENTATION,),
        review_surface="measurement",
        produced_artifact_types=("mesh-manifest", "mesh-baseline", "mesh-inference"),
        description="Convert segmented vertebrae into baseline and inference geometry.",
    ),
    PipelineStageName.LANDMARKS: PipelineStageSpec(
        stage=PipelineStageName.LANDMARKS,
        runner=run_landmarks_stage,
        dependencies=(PipelineStageName.MESH,),
        review_surface="measurement",
        backend_tool="landmarkpt",
        environment_id="landmarkpt",
        produced_artifact_types=("ptv3-vertebrae", "landmarks"),
        description="Infer dense PTv3 vertex groups and derive landmarks/primitives from them.",
    ),
    PipelineStageName.REGISTRATION: PipelineStageSpec(
        stage=PipelineStageName.REGISTRATION,
        runner=run_registration_stage,
        dependencies=(PipelineStageName.LANDMARKS,),
        review_surface="measurement",
        backend_tool="polypose",
        environment_id="polypose",
        produced_artifact_types=("registration", "registration-scene"),
        description="Register baseline vertebrae into a shared standing-frame pose graph.",
    ),
    PipelineStageName.MEASUREMENTS: PipelineStageSpec(
        stage=PipelineStageName.MEASUREMENTS,
        runner=run_measurements_stage,
        dependencies=(PipelineStageName.LANDMARKS,),
        review_surface="measurement",
        produced_artifact_types=("measurements",),
        description="Compute native 3D measurements from landmark-derived geometry.",
    ),
    PipelineStageName.FINDINGS: PipelineStageSpec(
        stage=PipelineStageName.FINDINGS,
        runner=run_findings_stage,
        dependencies=(PipelineStageName.MEASUREMENTS,),
        review_surface="report",
        produced_artifact_types=("findings",),
        description="Build review findings from valid and invalid measurement outputs.",
    ),
}


def get_stage_spec(stage: PipelineStageName) -> PipelineStageSpec:
    try:
        return STAGE_SPECS[stage]
    except KeyError as exc:
        raise ValueError(f"Unsupported analysis stage: {stage}") from exc


def expand_requested_stages(
    requested_stages: tuple[PipelineStageName, ...] | None,
) -> tuple[PipelineStageName, ...]:
    requested = requested_stages or DEFAULT_ANALYSIS_SEQUENCE
    ordered: list[PipelineStageName] = []
    seen: set[PipelineStageName] = set()

    def visit(stage: PipelineStageName) -> None:
        if stage in seen:
            return
        spec = get_stage_spec(stage)
        for dependency in spec.dependencies:
            visit(dependency)
        seen.add(stage)
        ordered.append(stage)

    for stage in requested:
        visit(stage)
    return tuple(stage for stage in DEFAULT_ANALYSIS_SEQUENCE if stage in seen and stage in ordered)


def downstream_stages(stage: PipelineStageName) -> tuple[PipelineStageName, ...]:
    graph: dict[PipelineStageName, list[PipelineStageName]] = {key: [] for key in STAGE_SPECS}
    for candidate, spec in STAGE_SPECS.items():
        for dependency in spec.dependencies:
            graph.setdefault(dependency, []).append(candidate)
    queue = deque([stage])
    ordered: list[PipelineStageName] = []
    seen: set[PipelineStageName] = set()
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        ordered.append(current)
        queue.extend(graph.get(current, []))
    return tuple(
        candidate for candidate in DEFAULT_ANALYSIS_SEQUENCE if candidate in seen
    )
