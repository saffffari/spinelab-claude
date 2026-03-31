from spinelab.models import CaseManifest
from spinelab.visualization.viewer_3d import MockVertebra
from spinelab.workspaces.report_model import build_report_dataset, build_report_dataset_from_models


def test_report_dataset_stays_placeholder_for_blank_case() -> None:
    dataset = build_report_dataset(CaseManifest.blank())

    assert dataset.has_pose_comparison is False
    assert dataset.has_measurements is False
    assert dataset.ordered_vertebrae == ()
    assert dataset.trend_series == ()
    assert dataset.regional_summaries == ()


def test_report_dataset_builds_sorted_trend_series_from_scene_models() -> None:
    manifest = CaseManifest.demo()
    scene_models = [
        MockVertebra("L1", "L1", (0.0, 0.0, 10.0), (1.0, 1.0, 1.0), pose_name="baseline"),
        MockVertebra("T1", "T1", (0.0, 0.0, 20.0), (1.0, 1.0, 1.0), pose_name="baseline"),
        MockVertebra("C7", "C7", (0.0, 0.0, 30.0), (1.0, 1.0, 1.0), pose_name="baseline"),
        MockVertebra(
            "L1",
            "L1 Standing",
            (0.0, 0.0, 13.0),
            (1.0, 1.0, 1.0),
            render_id="L1_STANDING",
            selection_id="L1",
            pose_name="standing",
        ),
        MockVertebra(
            "T1",
            "T1 Standing",
            (0.0, 2.0, 20.0),
            (1.0, 1.0, 1.0),
            render_id="T1_STANDING",
            selection_id="T1",
            pose_name="standing",
        ),
        MockVertebra(
            "C7",
            "C7 Standing",
            (1.0, 0.0, 30.0),
            (1.0, 1.0, 1.0),
            render_id="C7_STANDING",
            selection_id="C7",
            pose_name="standing",
        ),
    ]

    dataset = build_report_dataset_from_models(manifest, scene_models)
    trend_lookup = {series.key: series.values for series in dataset.trend_series}
    region_lookup = {summary.region_id: summary for summary in dataset.regional_summaries}

    assert dataset.has_pose_comparison is True
    assert dataset.ordered_vertebrae == ("C7", "T1", "L1")
    assert trend_lookup["dx"] == (1.0, 0.0, 0.0)
    assert trend_lookup["dy"] == (0.0, 2.0, 0.0)
    assert trend_lookup["dz"] == (0.0, 0.0, 3.0)
    assert region_lookup["cervical"].vertebra_ids == ("C7",)
    assert region_lookup["thoracic"].vertebra_ids == ("T1",)
    assert region_lookup["lumbar"].vertebra_ids == ("L1",)


def test_report_dataset_uses_structured_measurement_records_for_kpis() -> None:
    dataset = build_report_dataset(CaseManifest.demo())
    kpi_lookup = {card.key: card for card in dataset.kpis}

    assert dataset.has_measurements is True
    assert dataset.measurement_values["Cobb Angle"] == "42.0 deg"
    assert dataset.measurement_values["Lumbar Lordosis"] == "46.2 deg"
    assert kpi_lookup["cobb-angle"].value_text == "42.0 deg"
    assert kpi_lookup["cobb-angle"].delta_text == "Measurement Targets"
    assert "Demo Targets" in kpi_lookup["cobb-angle"].caption_text
    assert kpi_lookup["lumbar-lordosis"].value_text == "46.2 deg"
