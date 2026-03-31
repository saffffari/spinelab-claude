from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QPageSize, QPainter, QPdfWriter

from spinelab.models import CaseManifest, MetricRecord
from spinelab.ui.theme import GEOMETRY, THEME_COLORS, TYPOGRAPHY
from spinelab.visualization.viewer_3d import (
    MockVertebra,
    build_mock_mesh,
    build_pose_model_lookup,
    pv,
    reference_basis_for_model,
    scene_span_along_axis,
)


@dataclass(frozen=True, slots=True)
class MeasurementBundleResult:
    root: Path
    measurements_pdf_path: Path
    measurements_json_path: Path
    baseline_mesh_count: int
    standing_scene_count: int
    standing_projection_paths: dict[str, Path]
    warnings: tuple[str, ...]


def write_measurements_pdf(
    output_path: Path,
    manifest: CaseManifest,
    selected_measurements: list[tuple[str, str]],
) -> None:
    writer = QPdfWriter(str(output_path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.Letter))
    writer.setResolution(144)

    page_rect = writer.pageLayout().paintRectPixels(writer.resolution())
    margin = GEOMETRY.unit * 6
    y = margin

    painter = QPainter(writer)

    title_font = TYPOGRAPHY.create_font(20, TYPOGRAPHY.weight_semilight, display=True)
    body_font = TYPOGRAPHY.create_font(13, TYPOGRAPHY.weight_regular)
    label_font = TYPOGRAPHY.create_font(12, TYPOGRAPHY.weight_semilight)

    painter.setFont(title_font)
    painter.drawText(
        margin,
        y,
        f"SpineLab Measurements · {manifest.patient_name or 'Untitled Case'}",
    )
    y += GEOMETRY.unit * 5

    painter.setFont(body_font)
    painter.drawText(margin, y, f"Case ID: {manifest.case_id}")
    y += GEOMETRY.unit * 3
    painter.drawText(margin, y, f"Patient ID: {manifest.patient_id or 'Unassigned'}")
    y += GEOMETRY.unit * 3
    painter.drawText(margin, y, f"Diagnosis: {manifest.diagnosis or 'Unassigned'}")
    y += GEOMETRY.unit * 5

    painter.setFont(label_font)
    painter.drawText(margin, y, "Selected Measurements")
    y += GEOMETRY.unit * 4

    painter.setFont(body_font)
    line_height = GEOMETRY.unit * 3
    max_y = page_rect.height() - margin
    for measurement_name, measurement_value in selected_measurements:
        if y >= max_y:
            writer.newPage()
            y = margin
            painter.setFont(body_font)
        painter.drawText(margin, y, measurement_name)
        painter.drawText(
            QRect(page_rect.width() - margin - 240, y - line_height + 4, 220, line_height),
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            measurement_value,
        )
        y += line_height

    painter.end()


def export_measurement_bundle(
    bundle_root: Path,
    manifest: CaseManifest,
    *,
    selected_measurements: list[tuple[str, str]],
    baseline_mesh_files: list[Path],
    standing_scene_files: list[Path],
    standing_input_assets: dict[str, Path],
    scene_models: list[MockVertebra],
    selected_ids: set[str] | None = None,
    artifact_paths: dict[str, Path] | None = None,
    backend_provenance: dict[str, str] | None = None,
) -> MeasurementBundleResult:
    bundle_root.mkdir(parents=True, exist_ok=True)
    selected_lookup = {vertebra_id.upper() for vertebra_id in (selected_ids or set())}
    warnings: list[str] = []

    measurements_dir = bundle_root / "measurements"
    baseline_mesh_dir = bundle_root / "baseline-meshes"
    standing_scene_dir = bundle_root / "standing-scene"
    standing_input_dir = bundle_root / "standing-inputs"
    standing_drr_dir = bundle_root / "standing-drrs"
    artifacts_dir = bundle_root / "artifacts"
    for directory in (
        measurements_dir,
        baseline_mesh_dir,
        standing_scene_dir,
        standing_input_dir,
        standing_drr_dir,
        artifacts_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    baseline_mesh_count = 0
    for mesh_path in baseline_mesh_files:
        if mesh_path.parent.resolve() == baseline_mesh_dir.resolve():
            baseline_mesh_count += 1
            continue
        destination = _unique_path(baseline_mesh_dir / mesh_path.name)
        shutil.copy2(mesh_path, destination)
        baseline_mesh_count += 1

    standing_scene_count = 0
    for scene_path in standing_scene_files:
        destination = _unique_path(standing_scene_dir / scene_path.name)
        shutil.copy2(scene_path, destination)
        standing_scene_count += 1

    for role, asset_path in standing_input_assets.items():
        suffix = "".join(asset_path.suffixes) or ".dat"
        destination = _unique_path(standing_input_dir / f"{role}{suffix}")
        shutil.copy2(asset_path, destination)

    for artifact_name, artifact_path in sorted((artifact_paths or {}).items()):
        if not artifact_path.exists() or not artifact_path.is_file():
            continue
        destination = _unique_path(artifacts_dir / f"{artifact_name}{artifact_path.suffix}")
        shutil.copy2(artifact_path, destination)

    measurements_pdf_path = measurements_dir / f"{manifest.case_id}-measurements.pdf"
    write_measurements_pdf(measurements_pdf_path, manifest, selected_measurements)
    measurements_json_path = measurements_dir / f"{manifest.case_id}-measurements.json"
    _write_measurements_json(
        measurements_json_path,
        manifest,
        selected_measurements,
    )

    standing_models = [
        model
        for model in scene_models
        if model.pose_name == "standing"
        and (
            not selected_lookup
            or (
                model.selection_key is not None and model.selection_key.upper() in selected_lookup
            )
        )
    ]
    standing_projection_paths, projection_warnings = render_standing_biplanar_projections(
        standing_models,
        standing_drr_dir,
    )
    warnings.extend(projection_warnings)

    bundle_manifest_path = bundle_root / "bundle_manifest.json"
    bundle_manifest = {
        "case_id": manifest.case_id,
        "patient_name": manifest.patient_name,
        "selected_ids": sorted(selected_lookup),
        "segmentation_backend": dict(backend_provenance or {}),
        "measurements_pdf_path": _relative_string(bundle_root, measurements_pdf_path),
        "measurements_json_path": _relative_string(bundle_root, measurements_json_path),
        "baseline_mesh_count": baseline_mesh_count,
        "standing_scene_count": standing_scene_count,
        "standing_input_roles": sorted(standing_input_assets),
        "standing_drrs": {
            view_name: {
                "path": _relative_string(bundle_root, path),
                "generation_mode": "mesh_projection_scaffold",
                "note": (
                    "Current exports use orthographic standing mesh projections as a DRR scaffold. "
                    "Do not treat these as volume-integral NanoDRR outputs."
                ),
            }
            for view_name, path in standing_projection_paths.items()
        },
        "warnings": warnings,
    }
    bundle_manifest_path.write_text(json.dumps(bundle_manifest, indent=2), encoding="utf-8")

    return MeasurementBundleResult(
        root=bundle_root,
        measurements_pdf_path=measurements_pdf_path,
        measurements_json_path=measurements_json_path,
        baseline_mesh_count=baseline_mesh_count,
        standing_scene_count=standing_scene_count,
        standing_projection_paths=standing_projection_paths,
        warnings=tuple(warnings),
    )


def render_standing_biplanar_projections(
    standing_models: list[MockVertebra],
    output_dir: Path,
    *,
    image_size: tuple[int, int] = (1400, 1400),
) -> tuple[dict[str, Path], list[str]]:
    if not standing_models:
        return ({}, ["No standing scene available for bilateral projection export."])
    if pv is None:
        return ({}, ["PyVista is unavailable, so standing projections were skipped."])

    output_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    bounds = _scene_bounds(standing_models)
    focus = np.array(
        (
            (bounds[0] + bounds[1]) / 2.0,
            (bounds[2] + bounds[3]) / 2.0,
            (bounds[4] + bounds[5]) / 2.0,
        ),
        dtype=float,
    )
    model_lookup = build_pose_model_lookup(standing_models, pose_name="standing")
    reference_model = model_lookup.get("PELVIS")
    if reference_model is None and standing_models:
        reference_model = standing_models[0]
    basis = reference_basis_for_model(reference_model)
    scene_extents = np.array(
        (
            bounds[1] - bounds[0],
            bounds[3] - bounds[2],
            bounds[5] - bounds[4],
        ),
        dtype=float,
    )
    diagonal = max(
        float(np.linalg.norm(scene_extents)),
        1.0,
    )

    output_paths: dict[str, Path] = {}
    for view_name, direction, horizontal_axis in (
        ("ap", basis[:, 0], basis[:, 1]),
        ("lat", basis[:, 1], basis[:, 0]),
    ):
        try:
            plotter = pv.Plotter(off_screen=True, window_size=image_size)
            plotter.background_color = THEME_COLORS.viewport_bg
            for model in standing_models:
                mesh = build_mock_mesh(model)
                if mesh is None:
                    continue
                plotter.add_mesh(
                    mesh,
                    color=THEME_COLORS.text_primary,
                    opacity=1.0,
                    show_edges=False,
                    lighting=False,
                    reset_camera=False,
                    render=False,
                )
            camera = plotter.camera
            camera.parallel_projection = True
            camera.focal_point = tuple(float(value) for value in focus)
            camera.position = tuple(float(value) for value in (focus + direction * diagonal * 2.2))
            camera.up = tuple(float(value) for value in basis[:, 2])
            aspect_ratio = image_size[0] / max(image_size[1], 1)
            horizontal_min, horizontal_max = scene_span_along_axis(standing_models, horizontal_axis)
            vertical_min, vertical_max = scene_span_along_axis(standing_models, basis[:, 2])
            horizontal_span = max(horizontal_max - horizontal_min, 1.0)
            vertical_span = max(vertical_max - vertical_min, 1.0)
            camera.parallel_scale = max(
                vertical_span / 2.0,
                horizontal_span / max(2.0 * aspect_ratio, 1e-6),
                1.0,
            ) * 1.08
            output_path = output_dir / f"standing_{view_name}_scaffold.png"
            plotter.screenshot(str(output_path))
            output_paths[view_name] = output_path
        except Exception as exc:
            warnings.append(f"Unable to render standing {view_name.upper()} projection: {exc}")
        finally:
            try:
                plotter.close()
            except Exception:
                pass

    return output_paths, warnings


def _write_measurements_json(
    output_path: Path,
    manifest: CaseManifest,
    selected_measurements: list[tuple[str, str]],
) -> None:
    record_lookup = {
        (record.label or record.key): record for record in manifest.measurements.records
    }
    payload = {
        "case_id": manifest.case_id,
        "patient_name": manifest.patient_name,
        "measurement_count": len(selected_measurements),
        "measurements": [
            _metric_record_payload(record_lookup.get(label), label, value_text)
            for label, value_text in selected_measurements
        ],
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _metric_record_payload(
    record: MetricRecord | None,
    label: str,
    value_text: str,
) -> dict[str, object]:
    if record is None:
        return {"label": label, "value_text": value_text}
    return {
        "metric_id": record.metric_id,
        "key": record.key,
        "label": record.label or label,
        "value_text": record.value_text or value_text,
        "value": record.value,
        "unit": record.unit,
        "provenance": record.provenance,
        "source_stage": record.source_stage,
        "definition_version": record.definition_version,
        "measurement_mode": record.measurement_mode,
        "coordinate_frame": record.coordinate_frame,
        "valid": record.valid,
        "invalid_reason": record.invalid_reason,
        "uncertainty_text": record.uncertainty_text,
        "confidence": record.confidence,
        "source_artifact_ids": list(record.source_artifact_ids),
        "required_primitives": list(record.required_primitives),
    }


def _relative_string(root: Path, path: Path) -> str:
    return str(path.relative_to(root))


def _scene_bounds(
    models: list[MockVertebra],
) -> tuple[float, float, float, float, float, float]:
    bounds: list[tuple[float, float, float, float, float, float]] = []
    for model in models:
        mesh = build_mock_mesh(model)
        if mesh is not None:
            mesh_bounds = tuple(float(value) for value in mesh.bounds)
            bounds.append(
                (
                    mesh_bounds[0],
                    mesh_bounds[1],
                    mesh_bounds[2],
                    mesh_bounds[3],
                    mesh_bounds[4],
                    mesh_bounds[5],
                )
            )
            continue
        half_x, half_y, half_z = (extent / 2.0 for extent in model.extents)
        bounds.append(
            (
                model.center[0] - half_x,
                model.center[0] + half_x,
                model.center[1] - half_y,
                model.center[1] + half_y,
                model.center[2] - half_z,
                model.center[2] + half_z,
            )
        )
    if not bounds:
        return (-1.0, 1.0, -1.0, 1.0, -1.0, 1.0)
    return (
        min(bound[0] for bound in bounds),
        max(bound[1] for bound in bounds),
        min(bound[2] for bound in bounds),
        max(bound[3] for bound in bounds),
        min(bound[4] for bound in bounds),
        max(bound[5] for bound in bounds),
    )


def _unique_path(destination: Path) -> Path:
    if not destination.exists():
        return destination
    stem = destination.stem
    suffix = destination.suffix
    index = 1
    while True:
        candidate = destination.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1
