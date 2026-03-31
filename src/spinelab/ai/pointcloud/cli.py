from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from spinelab.ai.pointcloud.contracts import LandmarkInferencePayload, VertexGroupInferencePayload
from spinelab.ai.pointcloud.model import build_model
from spinelab.ai.pointcloud.preprocess import build_case_npz, build_dataset_from_root
from spinelab.ontology import (
    Modality,
    RegionId,
    StructureType,
    VariantTag,
    build_structure_instance_context,
    level_from_structure_instance_id,
    standard_structure_for_level,
)


def _json_load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object at {path}")
    return payload


def _json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _point_cloud_load(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".npz":
        with np.load(path, allow_pickle=False) as payload:
            return {key: payload[key] for key in payload.files}
    return _json_load(path)


def _structure_context_from_mesh_entry(
    mesh_entry: dict[str, Any],
    *,
    modality: str,
):
    from spinelab.ai.pointcloud.contracts import StructureContext

    structure_instance_id = str(
        mesh_entry.get("structure_instance_id")
        or mesh_entry.get("structure_id")
        or mesh_entry.get("vertebra_id")
    )
    display_label = str(mesh_entry.get("display_label") or mesh_entry.get("vertebra_id") or "")
    standard_level_id = str(mesh_entry.get("standard_level_id", "") or "") or None
    definition = standard_structure_for_level(standard_level_id)
    structure_type = (
        StructureType(str(mesh_entry["structure_type"]))
        if mesh_entry.get("structure_type")
        else definition.structure_type
        if definition is not None
        else StructureType.OTHER
    )
    order_index = int(mesh_entry["order_index"]) if mesh_entry.get("order_index") is not None else (
        definition.order_index if definition is not None else None
    )
    superior_neighbor = (
        mesh_entry.get("superior_neighbor_instance_id") or mesh_entry.get("superior_neighbor")
    )
    inferior_neighbor = (
        mesh_entry.get("inferior_neighbor_instance_id") or mesh_entry.get("inferior_neighbor")
    )
    numbering_confidence = float(mesh_entry.get("numbering_confidence", 1.0))
    parsed_variant_tags = tuple(
        VariantTag(str(item))
        for item in mesh_entry.get("variant_tags", [])
        if str(item) in {tag.value for tag in VariantTag}
    )
    context = build_structure_instance_context(
        structure_instance_id=structure_instance_id,
        display_label=display_label or structure_instance_id,
        modality=Modality(modality.upper()),
        numbering_confidence=numbering_confidence,
        variant_tags=parsed_variant_tags,
        superior_neighbor_instance_id=str(superior_neighbor) if superior_neighbor else None,
        inferior_neighbor_instance_id=str(inferior_neighbor) if inferior_neighbor else None,
    )
    region_id = (
        RegionId(str(mesh_entry["region_id"]))
        if mesh_entry.get("region_id")
        else context.region_id
    )
    supports_standard_measurements = bool(
        mesh_entry.get("supports_standard_measurements", context.supports_standard_measurements)
    )
    return StructureContext(
        structure_instance_id=structure_instance_id,
        display_label=display_label or context.display_label,
        standard_level_id=standard_level_id,
        region_id=region_id,
        structure_type=structure_type,
        order_index=order_index,
        modality=Modality(modality.upper()),
        numbering_confidence=numbering_confidence,
        variant_tags=parsed_variant_tags or context.variant_tags,
        supports_standard_measurements=supports_standard_measurements,
        superior_neighbor_instance_id=str(superior_neighbor) if superior_neighbor else None,
        inferior_neighbor_instance_id=str(inferior_neighbor) if inferior_neighbor else None,
    )


def run_infer_landmarks(args: argparse.Namespace) -> int:
    mesh_manifest = _json_load(Path(args.mesh_manifest))
    provider_name = args.provider
    model = build_model(
        provider_name,
        weights_path=Path(args.weights) if args.weights else None,
        config_path=Path(args.config) if args.config else None,
    )

    ptv3_entries: list[dict[str, Any]] = []
    landmark_entries: list[dict[str, Any]] = []
    modality = str(mesh_manifest.get("modality", "CT"))
    for mesh_entry in mesh_manifest.get("vertebrae", []):
        point_cloud_path = Path(str(mesh_entry["point_cloud_path"]))
        point_cloud_payload = _point_cloud_load(point_cloud_path)
        points_key = "points_mm" if "points_mm" in point_cloud_payload else "points"
        points_xyz = np.asarray(point_cloud_payload[points_key], dtype=float)
        context = _structure_context_from_mesh_entry(mesh_entry, modality=modality)
        prediction = model.predict_structure(points_xyz=points_xyz, context=context)
        level_id = (
            context.standard_level_id
            or level_from_structure_instance_id(context.structure_instance_id)
            or context.structure_instance_id
        )
        ptv3_entries.append(
            {
                "vertebra_id": str(mesh_entry.get("vertebra_id") or level_id),
                "structure_instance_id": context.structure_instance_id,
                "display_label": context.display_label,
                "standard_level_id": context.standard_level_id,
                "region_id": context.region_id.value,
                "numbering_confidence": context.numbering_confidence,
                "variant_tags": [tag.value for tag in context.variant_tags],
                "is_atypical": context.is_atypical,
                "supports_standard_measurements": context.supports_standard_measurements,
                "coordinate_frame": str(mesh_entry.get("coordinate_frame", "patient-body-supine")),
                "model_name": args.model_name,
                "model_version": args.model_version,
                "confidence": prediction.confidence,
                "vertex_groups": prediction.vertex_groups,
                "qc_summary": prediction.qc_summary,
            }
        )
        landmark_entries.append(
            {
                "vertebra_id": str(mesh_entry.get("vertebra_id") or level_id),
                "structure_instance_id": context.structure_instance_id,
                "display_label": context.display_label,
                "standard_level_id": context.standard_level_id,
                "region_id": context.region_id.value,
                "numbering_confidence": context.numbering_confidence,
                "variant_tags": [tag.value for tag in context.variant_tags],
                "is_atypical": context.is_atypical,
                "supports_standard_measurements": context.supports_standard_measurements,
                "coordinate_frame": str(mesh_entry.get("coordinate_frame", "patient-body-supine")),
                "supporting_artifact_ids": (
                    [str(args.source_artifact_id)] if args.source_artifact_id else []
                ),
                "supporting_vertex_groups": list(prediction.vertex_groups),
                "primitives": prediction.primitives,
                "quality": {
                    "confidence": prediction.confidence,
                    **prediction.qc_summary,
                },
            }
        )

    from spinelab.ai.pointcloud.geometry import derive_global_structures

    ptv3_payload = VertexGroupInferencePayload(
        case_id=args.case_id or str(mesh_manifest.get("case_id", "unknown-case")),
        model_name=args.model_name,
        model_version=args.model_version,
        provider_name=model.provider_name,
        vertebrae=tuple(ptv3_entries),
        notes=("Heuristic provider is active until trained PTv3 weights are configured.",)
        if model.provider_name == "heuristic"
        else (),
    )
    landmark_payload = LandmarkInferencePayload(
        case_id=args.case_id or str(mesh_manifest.get("case_id", "unknown-case")),
        model_name=args.model_name,
        model_version=args.model_version,
        provider_name=model.provider_name,
        coordinate_frame=str(mesh_manifest.get("coordinate_frame", "patient-body-supine")),
        vertebrae=tuple(landmark_entries),
        global_structures=tuple(derive_global_structures(landmark_entries)),
        notes=("Standard contract spans C7-S1; C1-C6 remain unsupported extras.",),
    )
    _json_write(Path(args.output_ptv3), ptv3_payload.to_dict())
    _json_write(Path(args.output_landmarks), landmark_payload.to_dict())
    return 0


def run_preprocess_case(args: argparse.Namespace) -> int:
    written = build_case_npz(
        metadata_path=Path(args.metadata),
        output_dir=Path(args.output_dir),
        image_path=Path(args.image) if args.image else None,
        structures_path=Path(args.structures) if args.structures else None,
        surface_patches_path=Path(args.surface_patches) if args.surface_patches else None,
        landmarks_path=Path(args.landmarks) if args.landmarks else None,
        max_points=args.max_points,
        seed=args.seed,
    )
    print(json.dumps({"written": [str(path) for path in written]}, indent=2))
    return 0


def run_build_dataset(args: argparse.Namespace) -> int:
    written = build_dataset_from_root(
        cases_root=Path(args.cases_root),
        output_dir=Path(args.output_dir),
        max_points=args.max_points,
        seed=args.seed,
    )
    print(json.dumps({"written": [str(path) for path in written]}, indent=2))
    return 0


def run_train(args: argparse.Namespace) -> int:
    provider = build_model(
        args.provider,
        weights_path=Path(args.weights) if args.weights else None,
        config_path=Path(args.config) if args.config else None,
    )
    payload = {
        "provider_name": provider.provider_name,
        "dataset_root": str(Path(args.dataset_root)),
        "status": "scaffolded",
        "message": (
            "Training entrypoint is wired for config validation and provider selection; "
            "optimizer and loop integration remain TODO until PTv3 weights land."
        ),
    }
    print(json.dumps(payload, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SpineLab point-cloud utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    preprocess_case = subparsers.add_parser("preprocess-case", help="Build one case package.")
    preprocess_case.add_argument("--metadata", required=True)
    preprocess_case.add_argument("--output-dir", required=True)
    preprocess_case.add_argument("--image")
    preprocess_case.add_argument("--structures")
    preprocess_case.add_argument("--surface-patches")
    preprocess_case.add_argument("--landmarks")
    preprocess_case.add_argument("--max-points", type=int, default=4096)
    preprocess_case.add_argument("--seed", type=int, default=7)
    preprocess_case.set_defaults(func=run_preprocess_case)

    build_dataset = subparsers.add_parser("build-dataset", help="Build a dataset tree from cases.")
    build_dataset.add_argument("--cases-root", required=True)
    build_dataset.add_argument("--output-dir", required=True)
    build_dataset.add_argument("--max-points", type=int, default=4096)
    build_dataset.add_argument("--seed", type=int, default=7)
    build_dataset.set_defaults(func=run_build_dataset)

    infer_landmarks = subparsers.add_parser("infer-landmarks", help="Run landmark inference.")
    infer_landmarks.add_argument("--mesh-manifest", required=True)
    infer_landmarks.add_argument("--output-ptv3", required=True)
    infer_landmarks.add_argument("--output-landmarks", required=True)
    infer_landmarks.add_argument("--provider", default="heuristic")
    infer_landmarks.add_argument("--model-name", default="point-transformer-v3")
    infer_landmarks.add_argument("--model-version", default="contract-scaffold.v1")
    infer_landmarks.add_argument("--config")
    infer_landmarks.add_argument("--weights")
    infer_landmarks.add_argument("--case-id")
    infer_landmarks.add_argument("--source-artifact-id")
    infer_landmarks.set_defaults(func=run_infer_landmarks)

    train = subparsers.add_parser("train", help="Validate PTv3 training config scaffolding.")
    train.add_argument("--dataset-root", required=True)
    train.add_argument("--provider", default="pointcept")
    train.add_argument("--config")
    train.add_argument("--weights")
    train.set_defaults(func=run_train)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
