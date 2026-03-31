from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np

from spinelab.io.case_store import DEFAULT_DATA_ROOT
from spinelab.pipeline.stages.mesh_pipeline import (
    BENCHMARK_EXTRACTION_ALGORITHMS,
    MeshPipelineConfig,
    affine_components,
    binary_surface_distance_metrics,
    dice_score,
    extract_vertebra_mesh,
    hydrate_segmentation_entries,
    label_statistics_for_entries,
    load_label_map,
    parse_segmentation_entries,
    rasterize_polydata,
    sample_point_cloud,
)
from spinelab.services import configure_runtime_policy


def _discover_segmentation_manifests(inputs: list[str]) -> list[Path]:
    if not inputs:
        search_root = DEFAULT_DATA_ROOT / "cases"
        return sorted(search_root.glob("*/analytics/derived/segmentation/segmentation.json"))

    manifests: list[Path] = []
    seen: set[Path] = set()
    for raw_input in inputs:
        candidate = Path(raw_input)
        discovered: list[Path] = []
        if candidate.is_file() and candidate.name.lower() == "segmentation.json":
            discovered = [candidate]
        elif candidate.is_dir():
            direct = candidate / "segmentation.json"
            if direct.is_file():
                discovered = [direct]
            else:
                discovered = sorted(candidate.rglob("segmentation.json"))
        for manifest_path in discovered:
            resolved = manifest_path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                manifests.append(resolved)
    return manifests


def _summarize_algorithm(records: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [record for record in records if record.get("status") == "complete"]
    if not complete:
        return {"vertebra_count": 0, "complete_count": 0}

    runtimes = [float(record["elapsed_seconds"]) for record in complete]
    triangles = [int(record["triangle_count"]) for record in complete]
    dice_values = [float(record["dice"]) for record in complete]
    assd_values = [
        float(record["assd_mm"]) for record in complete if record.get("assd_mm") is not None
    ]
    hd95_values = [
        float(record["hd95_mm"]) for record in complete if record.get("hd95_mm") is not None
    ]
    max_hd_values = [
        float(record["max_hd_mm"]) for record in complete if record.get("max_hd_mm") is not None
    ]
    qc_passes = [
        record
        for record in complete
        if int(record.get("component_count", 0)) == 1 and bool(record.get("watertight", False))
    ]
    deterministic = [bool(record["point_cloud_deterministic"]) for record in complete]
    return {
        "vertebra_count": len(records),
        "complete_count": len(complete),
        "median_runtime_seconds": round(median(runtimes), 6),
        "median_triangle_count": int(median(triangles)),
        "mean_dice": round(float(sum(dice_values) / len(dice_values)), 6),
        "mean_assd_mm": (
            round(float(sum(assd_values) / len(assd_values)), 6) if assd_values else None
        ),
        "mean_hd95_mm": (
            round(float(sum(hd95_values) / len(hd95_values)), 6) if hd95_values else None
        ),
        "mean_max_hd_mm": (
            round(float(sum(max_hd_values) / len(max_hd_values)), 6) if max_hd_values else None
        ),
        "qc_pass_rate": round(float(len(qc_passes) / len(complete)), 6),
        "point_cloud_determinism_rate": round(
            float(sum(1 for value in deterministic if value) / len(deterministic)),
            6,
        ),
    }


def _write_summary_markdown(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Mesh Benchmark Summary",
        "",
        f"Generated at: {summary['generated_at']}",
        "",
    ]
    for algorithm, algorithm_summary in summary["algorithms"].items():
        lines.extend(
            [
                f"## {algorithm}",
                "",
                f"- Complete vertebrae: {algorithm_summary.get('complete_count', 0)}",
                f"- Median runtime (s): {algorithm_summary.get('median_runtime_seconds')}",
                f"- Median triangles: {algorithm_summary.get('median_triangle_count')}",
                f"- Mean Dice: {algorithm_summary.get('mean_dice')}",
                f"- Mean ASSD (mm): {algorithm_summary.get('mean_assd_mm')}",
                f"- Mean HD95 (mm): {algorithm_summary.get('mean_hd95_mm')}",
                f"- QC pass rate: {algorithm_summary.get('qc_pass_rate')}",
                f"- Point-cloud determinism rate: "
                f"{algorithm_summary.get('point_cloud_determinism_rate')}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark SpineLab vertebra mesh extraction candidates on one or more "
            "segmentation contracts."
        )
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help=(
            "Segmentation manifest paths or directories containing segmentation.json. "
            "When omitted, the tool scans managed cases under the data root."
        ),
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_DATA_ROOT / "raw_test_data" / "_benchmarks" / "mesh_pipeline"),
        help="Directory where the benchmark run output should be written.",
    )
    parser.add_argument(
        "--point-count",
        type=int,
        default=4096,
        help="Number of PTv3-style surface samples to generate for determinism checks.",
    )
    args = parser.parse_args()

    manifests = _discover_segmentation_manifests(args.inputs)
    if not manifests:
        raise SystemExit("No segmentation manifests found for benchmarking.")

    configure_runtime_policy()
    config = MeshPipelineConfig(point_cloud_size=max(256, int(args.point_count)))
    run_dir = Path(args.output_root) / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    all_records: list[dict[str, Any]] = []
    for manifest_path in manifests:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        label_map_path = Path(str(payload["label_map_path"]))
        if not label_map_path.is_absolute():
            label_map_path = (manifest_path.parent / label_map_path).resolve()
        label_map, affine = load_label_map(label_map_path)
        parsed_entries = parse_segmentation_entries(payload)
        entries = hydrate_segmentation_entries(
            parsed_entries,
            label_statistics_for_entries(label_map, parsed_entries),
            affine,
        )
        for algorithm in BENCHMARK_EXTRACTION_ALGORITHMS:
            for entry in entries:
                point_cloud_seed_prefix = f"{manifest_path}:{algorithm}"
                point_cloud_seed_key = (
                    f"{point_cloud_seed_prefix}:{entry.vertebra_id}:{entry.label_value}"
                )
                result = extract_vertebra_mesh(
                    label_map,
                    affine,
                    entry,
                    algorithm=algorithm,
                    config=config,
                    point_cloud_seed_key=point_cloud_seed_prefix,
                )
                record: dict[str, Any] = {
                    "segmentation_manifest": str(manifest_path),
                    "algorithm": algorithm,
                    "vertebra_id": entry.vertebra_id,
                    "label_value": entry.label_value,
                    "status": result.status,
                    "elapsed_seconds": round(float(result.elapsed_seconds), 6),
                }
                if result.status != "complete":
                    all_records.append(record)
                    continue

                assert result.measurement_mesh is not None
                assert result.point_cloud is not None
                assert result.point_normals is not None
                assert result.mesh_stats is not None
                assert result.qc_summary is not None

                revoxelized = rasterize_polydata(
                    result.measurement_mesh,
                    shape=result.roi_mask.shape,
                    affine=result.roi_affine,
                )
                _, _, spacing = affine_components(result.roi_affine)
                surface_metrics = binary_surface_distance_metrics(
                    result.roi_mask,
                    revoxelized,
                    spacing=spacing,
                )
                sampled_points, sampled_normals = sample_point_cloud(
                    result.measurement_mesh,
                    sample_count=config.point_cloud_size,
                    seed_key=point_cloud_seed_key,
                )
                deterministic = bool(
                    np.array_equal(result.point_cloud, sampled_points)
                    and np.array_equal(result.point_normals, sampled_normals)
                )
                record.update(
                    {
                        "triangle_count": int(result.mesh_stats["triangle_count"]),
                        "point_count": int(result.mesh_stats["point_count"]),
                        "component_count": int(
                            result.qc_summary["component_summary"]["component_count"]
                        ),
                        "watertight": bool(
                            result.qc_summary["component_summary"]["watertight"]
                        ),
                        "dice": round(float(dice_score(result.roi_mask, revoxelized)), 6),
                        "assd_mm": surface_metrics["assd_mm"],
                        "hd95_mm": surface_metrics["hd95_mm"],
                        "max_hd_mm": surface_metrics["max_hd_mm"],
                        "point_cloud_deterministic": deterministic,
                    }
                )
                all_records.append(record)

    summary = {
        "generated_at": datetime.now().isoformat(),
        "config": {
            "point_cloud_size": config.point_cloud_size,
            "algorithms": list(BENCHMARK_EXTRACTION_ALGORITHMS),
        },
        "inputs": [str(path) for path in manifests],
        "algorithms": {
            algorithm: _summarize_algorithm(
                [record for record in all_records if record["algorithm"] == algorithm]
            )
            for algorithm in BENCHMARK_EXTRACTION_ALGORITHMS
        },
    }

    per_vertebra_path = run_dir / "per_vertebra.json"
    summary_path = run_dir / "summary.json"
    markdown_path = run_dir / "summary.md"
    per_vertebra_path.write_text(json.dumps(all_records, indent=2), encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_summary_markdown(markdown_path, summary)

    print(f"Wrote benchmark results to {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
