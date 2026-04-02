import json
from pathlib import Path

from spinelab.exports.measurement_bundle import (
    MeasurementBundleResult,
    export_measurement_bundle,
)
from spinelab.models import CaseManifest, StudyAsset
from spinelab.visualization.viewer_3d import MockVertebra
from spinelab.workspaces.measurement_workspace import write_mock_box_ply


def test_export_measurement_bundle_writes_structured_data_root_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    mesh_path = tmp_path / "L1.ply"
    write_mock_box_ply(
        mesh_path,
        MockVertebra("L1", "L1", (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)),
    )
    standing_scene_path = tmp_path / "standing_scene.glb"
    standing_scene_path.write_bytes(b"glb")
    ap_input = tmp_path / "standing_ap.png"
    ap_input.write_bytes(b"png")
    lat_input = tmp_path / "standing_lat.png"
    lat_input.write_bytes(b"png")
    measurements_artifact = tmp_path / "measurements.json"
    measurements_artifact.write_text("{}", encoding="utf-8")

    manifest = CaseManifest.demo()
    manifest.assets.extend(
        [
            StudyAsset(
                asset_id="ap-input",
                kind="xray_2d",
                label="X-Ray",
                source_path=str(ap_input),
                managed_path=str(ap_input),
                processing_role="xray_ap",
            ),
            StudyAsset(
                asset_id="lat-input",
                kind="xray_2d",
                label="X-Ray",
                source_path=str(lat_input),
                managed_path=str(lat_input),
                processing_role="xray_lat",
            ),
        ]
    )

    def fake_render(standing_models, output_dir, *, image_size=(1400, 1400)):
        del standing_models, image_size
        output_dir.mkdir(parents=True, exist_ok=True)
        ap_path = output_dir / "standing_ap_scaffold.png"
        lat_path = output_dir / "standing_lat_scaffold.png"
        ap_path.write_bytes(b"ap")
        lat_path.write_bytes(b"lat")
        return ({"ap": ap_path, "lat": lat_path}, [])

    monkeypatch.setattr(
        "spinelab.exports.measurement_bundle.render_standing_biplanar_projections",
        fake_render,
    )
    monkeypatch.setattr(
        "spinelab.exports.measurement_bundle.write_measurements_pdf",
        lambda output_path, manifest, selected_measurements: output_path.write_bytes(b"pdf"),
    )

    bundle_root = tmp_path / "outputs" / "case-001"
    result = export_measurement_bundle(
        bundle_root,
        manifest,
        selected_measurements=[("Cobb Angle", "42.0 deg")],
        baseline_mesh_files=[mesh_path],
        standing_scene_files=[standing_scene_path],
        standing_input_assets={
            "standing_ap_input": ap_input,
            "standing_lat_input": lat_input,
        },
        scene_models=[
            MockVertebra(
                "PELVIS",
                "Pelvis Standing",
                (0.0, 0.0, 0.0),
                (2.0, 2.0, 1.0),
                pose_name="standing",
            ),
            MockVertebra(
                "L1",
                "L1 Standing",
                (0.0, 0.0, 2.0),
                (1.0, 1.0, 1.0),
                pose_name="standing",
            ),
        ],
        artifact_paths={"measurements": measurements_artifact},
        backend_provenance={
            "backend_id": "cads-skeleton",
            "display_name": "CADS Skeleton",
            "checkpoint_id": "fold-1:checkpoint_final",
        },
    )

    assert isinstance(result, MeasurementBundleResult)
    assert (bundle_root / "baseline-meshes" / "L1.ply").exists() is True
    assert (bundle_root / "standing-scene" / "standing_scene.glb").exists() is True
    assert (bundle_root / "standing-inputs" / "standing_ap_input.png").exists() is True
    assert (bundle_root / "standing-inputs" / "standing_lat_input.png").exists() is True
    assert (bundle_root / "standing-drrs" / "standing_ap_scaffold.png").exists() is True
    assert (bundle_root / "standing-drrs" / "standing_lat_scaffold.png").exists() is True
    assert result.measurements_pdf_path.exists() is True
    assert result.measurements_json_path.exists() is True

    bundle_manifest = json.loads((bundle_root / "bundle_manifest.json").read_text(encoding="utf-8"))
    assert bundle_manifest["standing_drrs"]["ap"]["generation_mode"] == "mesh_projection_scaffold"
    assert bundle_manifest["standing_drrs"]["lat"]["generation_mode"] == "mesh_projection_scaffold"
    assert bundle_manifest["baseline_mesh_count"] == 1
    assert bundle_manifest["standing_scene_count"] == 1
    assert bundle_manifest["segmentation_backend"]["backend_id"] == "cads-skeleton"
