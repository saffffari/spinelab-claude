from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from spinelab.models import CaseManifest, MetricRecord
from spinelab.ui.theme import THEME_COLORS
from spinelab.workspaces.measurement_workspace import (
    build_selection_model_index,
    measurement_record_label,
    measurement_records_for_manifest,
    measurement_scene_sort_key,
    models_for_manifest,
)

REPORT_SECTION_IDS = (
    "overview",
    "alignment",
    "regional",
    "vertebral",
    "export",
)
REPORT_METRIC_KEYS = ("dx", "dy", "dz", "magnitude")
REGION_ORDER = ("cervical", "thoracic", "lumbar", "pelvis", "other")
REGION_LABELS = {
    "cervical": "Cervical",
    "thoracic": "Thoracic",
    "lumbar": "Lumbar",
    "pelvis": "Pelvis",
    "other": "Other",
}
REGION_COLORS = {
    "cervical": THEME_COLORS.info,
    "thoracic": THEME_COLORS.success,
    "lumbar": THEME_COLORS.focus,
    "pelvis": THEME_COLORS.warning,
    "other": THEME_COLORS.text_secondary,
}
TREND_SERIES_COLORS = {
    "dx": THEME_COLORS.info,
    "dy": THEME_COLORS.success,
    "dz": THEME_COLORS.focus,
    "magnitude": THEME_COLORS.warning,
}
TREND_SERIES_LABELS = {
    "dx": "ΔX",
    "dy": "ΔY",
    "dz": "ΔZ",
    "magnitude": "Magnitude",
}


@dataclass(frozen=True)
class KpiCardData:
    key: str
    title: str
    value_text: str
    delta_text: str
    caption_text: str
    accent_color: str
    spark_values: tuple[float, ...]


@dataclass(frozen=True)
class VertebraTrendSeries:
    key: str
    label: str
    color: str
    values: tuple[float, ...]


@dataclass(frozen=True)
class RegionalSummaryData:
    region_id: str
    label: str
    color: str
    vertebra_ids: tuple[str, ...]
    average_magnitude: float
    peak_magnitude: float
    total_magnitude: float


@dataclass(frozen=True)
class PoseDeltaGlyphData:
    vertebra_id: str
    label: str
    region_id: str
    color: str
    start: tuple[float, float, float]
    delta: tuple[float, float, float]
    magnitude: float


@dataclass(frozen=True)
class ReportDataset:
    case_id: str
    patient_name: str
    diagnosis: str
    summary_text: str
    notes_seed: str
    ordered_vertebrae: tuple[str, ...]
    kpis: tuple[KpiCardData, ...]
    trend_series: tuple[VertebraTrendSeries, ...]
    regional_summaries: tuple[RegionalSummaryData, ...]
    glyphs: tuple[PoseDeltaGlyphData, ...]
    measurement_records: tuple[MetricRecord, ...]
    measurement_values: dict[str, str]
    status_lines: tuple[str, ...]
    dominant_region_id: str | None
    has_pose_comparison: bool
    has_measurements: bool


@dataclass(frozen=True)
class ReportViewState:
    section_id: str = "overview"
    active_metric_keys: tuple[str, ...] = REPORT_METRIC_KEYS
    selected_vertebra_id: str | None = None
    selected_region_id: str | None = None
    viewport_axis_mode: str = "perspective"


def build_report_dataset(manifest: CaseManifest) -> ReportDataset:
    return build_report_dataset_from_models(manifest, models_for_manifest(manifest))


def build_pending_report_dataset(manifest: CaseManifest) -> ReportDataset:
    diagnosis = manifest.diagnosis or "Analyze required"
    summary_text = f"{manifest.patient_name or 'Untitled Case'} · {diagnosis}"
    return ReportDataset(
        case_id=manifest.case_id,
        patient_name=manifest.patient_name or "Untitled Case",
        diagnosis=diagnosis,
        summary_text=summary_text,
        notes_seed="",
        ordered_vertebrae=(),
        kpis=(),
        trend_series=(),
        regional_summaries=(),
        glyphs=(),
        measurement_records=(),
        measurement_values={},
        status_lines=("Run Analyze in Import to unlock report data.",),
        dominant_region_id=None,
        has_pose_comparison=False,
        has_measurements=False,
    )


def build_report_dataset_from_models(
    manifest: CaseManifest,
    scene_models,
) -> ReportDataset:
    baseline_index = build_selection_model_index(scene_models, pose_name="baseline")
    standing_index = build_selection_model_index(scene_models, pose_name="standing")
    ordered_vertebrae = tuple(
        sorted(
            set(baseline_index) | set(standing_index),
            key=measurement_scene_sort_key,
        )
    )
    has_pose_comparison = bool(ordered_vertebrae) and bool(standing_index)

    trend_values: dict[str, list[float]] = {
        metric_key: [] for metric_key in REPORT_METRIC_KEYS
    }
    glyphs: list[PoseDeltaGlyphData] = []
    for vertebra_id in ordered_vertebrae:
        baseline = baseline_index.get(vertebra_id)
        standing = standing_index.get(vertebra_id)
        if baseline is None or standing is None:
            delta = (0.0, 0.0, 0.0)
        else:
            delta = (
                standing.center[0] - baseline.center[0],
                standing.center[1] - baseline.center[1],
                standing.center[2] - baseline.center[2],
            )
        magnitude = sqrt((delta[0] ** 2) + (delta[1] ** 2) + (delta[2] ** 2))
        trend_values["dx"].append(delta[0])
        trend_values["dy"].append(delta[1])
        trend_values["dz"].append(delta[2])
        trend_values["magnitude"].append(magnitude)

        if has_pose_comparison and baseline is not None and standing is not None:
            region_id = classify_region(vertebra_id)
            glyphs.append(
                PoseDeltaGlyphData(
                    vertebra_id=vertebra_id,
                    label=vertebra_id,
                    region_id=region_id,
                    color=REGION_COLORS[region_id],
                    start=baseline.center,
                    delta=delta,
                    magnitude=magnitude,
                )
            )

    trend_series = tuple(
        VertebraTrendSeries(
            key=metric_key,
            label=TREND_SERIES_LABELS[metric_key],
            color=TREND_SERIES_COLORS[metric_key],
            values=tuple(trend_values[metric_key]),
        )
        for metric_key in REPORT_METRIC_KEYS
        if has_pose_comparison
    )
    regional_summaries = build_regional_summaries(glyphs)
    measurement_records = measurement_records_for_manifest(manifest)
    measurement_values = {
        measurement_record_label(record): record.value_text
        for record in measurement_records
        if record.value_text
    }
    kpis = build_kpi_cards(manifest, measurement_records, trend_values, regional_summaries)
    dominant_region_id = (
        max(regional_summaries, key=lambda item: item.total_magnitude).region_id
        if regional_summaries
        else None
    )
    diagnosis = manifest.diagnosis or "No diagnosis recorded"
    summary_text = f"{manifest.patient_name or 'Untitled Case'} · {diagnosis}"
    notes_seed = build_notes_seed(manifest, regional_summaries, trend_values)

    return ReportDataset(
        case_id=manifest.case_id,
        patient_name=manifest.patient_name or "Untitled Case",
        diagnosis=diagnosis,
        summary_text=summary_text,
        notes_seed=notes_seed,
        ordered_vertebrae=ordered_vertebrae,
        kpis=kpis,
        trend_series=trend_series,
        regional_summaries=regional_summaries,
        glyphs=tuple(glyphs),
        measurement_records=measurement_records,
        measurement_values=measurement_values,
        status_lines=tuple(summarize_pipeline_runs(manifest)),
        dominant_region_id=dominant_region_id,
        has_pose_comparison=has_pose_comparison,
        has_measurements=bool(measurement_values),
    )


def build_kpi_cards(
    manifest: CaseManifest,
    measurement_records: tuple[MetricRecord, ...],
    trend_values: dict[str, list[float]],
    regional_summaries: tuple[RegionalSummaryData, ...],
) -> tuple[KpiCardData, ...]:
    magnitude_values = tuple(trend_values.get("magnitude", []))
    total_motion = sum(magnitude_values) if magnitude_values else 0.0
    peak_motion = max(magnitude_values, default=0.0)
    dominant_region = (
        max(regional_summaries, key=lambda item: item.total_magnitude).label
        if regional_summaries
        else "No comparison scene"
    )
    measurement_lookup = {
        measurement_record_label(record): record for record in measurement_records
    }
    cards = [
        KpiCardData(
            key="cobb-angle",
            title="Cobb Angle",
            value_text=metric_card_value(
                measurement_lookup.get("Cobb Angle"),
                manifest.cobb_angle or "--",
            ),
            delta_text=metric_card_stage_text(measurement_lookup.get("Cobb Angle")),
            caption_text=metric_card_caption_text(
                measurement_lookup.get("Cobb Angle"),
                manifest.patient_id or manifest.case_id,
            ),
            accent_color=THEME_COLORS.focus,
            spark_values=magnitude_values,
        ),
        KpiCardData(
            key="pelvic-tilt",
            title="Pelvic Tilt",
            value_text=metric_card_value(measurement_lookup.get("Pelvic Tilt"), "--"),
            delta_text=metric_card_stage_text(measurement_lookup.get("Pelvic Tilt")),
            caption_text=metric_card_caption_text(
                measurement_lookup.get("Pelvic Tilt"),
                dominant_region,
            ),
            accent_color=THEME_COLORS.warning,
            spark_values=tuple(trend_values.get("dz", ())),
        ),
        KpiCardData(
            key="sva",
            title="Sagittal Vertical Axis",
            value_text=metric_card_value(
                measurement_lookup.get("Sagittal Vertical Axis"),
                "--",
            ),
            delta_text=metric_card_stage_text(
                measurement_lookup.get("Sagittal Vertical Axis")
            ),
            caption_text=metric_card_caption_text(
                measurement_lookup.get("Sagittal Vertical Axis"),
                "Global alignment",
            ),
            accent_color=THEME_COLORS.success,
            spark_values=tuple(trend_values.get("dy", ())),
        ),
        KpiCardData(
            key="thoracic-kyphosis",
            title="Thoracic Kyphosis",
            value_text=metric_card_value(
                measurement_lookup.get("Thoracic Kyphosis"),
                "--",
            ),
            delta_text=metric_card_stage_text(measurement_lookup.get("Thoracic Kyphosis")),
            caption_text=metric_card_caption_text(
                measurement_lookup.get("Thoracic Kyphosis"),
                "Thoracic region",
            ),
            accent_color=THEME_COLORS.info,
            spark_values=tuple(thoracic_sparkline(regional_summaries)),
        ),
        KpiCardData(
            key="lumbar-lordosis",
            title="Lumbar Lordosis",
            value_text=metric_card_value(
                measurement_lookup.get("Lumbar Lordosis"),
                "--",
            ),
            delta_text=metric_card_stage_text(measurement_lookup.get("Lumbar Lordosis")),
            caption_text=metric_card_caption_text(
                measurement_lookup.get("Lumbar Lordosis"),
                "Lumbar region",
            ),
            accent_color=THEME_COLORS.danger,
            spark_values=tuple(lumbar_sparkline(regional_summaries)),
        ),
        KpiCardData(
            key="total-motion",
            title="Total Pose Delta",
            value_text=format_distance(total_motion) if magnitude_values else "--",
            delta_text=(
                f"Peak {format_distance(peak_motion)}"
                if magnitude_values
                else "No motion scene"
            ),
            caption_text=dominant_region,
            accent_color=THEME_COLORS.focus,
            spark_values=magnitude_values,
        ),
    ]
    return tuple(cards)


def metric_card_value(record: MetricRecord | None, fallback: str) -> str:
    if record is not None and record.value_text:
        return record.value_text
    return fallback or "--"


def metric_card_stage_text(record: MetricRecord | None) -> str:
    if record is None or not record.source_stage:
        return "No metric output"
    return record.source_stage.replace("_", " ").title()


def metric_card_caption_text(record: MetricRecord | None, fallback_context: str) -> str:
    if record is None:
        return fallback_context
    parts: list[str] = []
    if record.provenance:
        parts.append(record.provenance.replace("_", " ").title())
    if record.confidence is not None:
        parts.append(f"{record.confidence * 100:.0f}% conf")
    if fallback_context and fallback_context not in parts:
        parts.append(fallback_context)
    return " · ".join(parts) if parts else fallback_context


def thoracic_sparkline(regional_summaries: tuple[RegionalSummaryData, ...]) -> tuple[float, ...]:
    for summary in regional_summaries:
        if summary.region_id == "thoracic":
            return (
                summary.average_magnitude,
                summary.total_magnitude,
                summary.peak_magnitude,
            )
    return ()


def lumbar_sparkline(regional_summaries: tuple[RegionalSummaryData, ...]) -> tuple[float, ...]:
    for summary in regional_summaries:
        if summary.region_id == "lumbar":
            return (
                summary.average_magnitude,
                summary.total_magnitude,
                summary.peak_magnitude,
            )
    return ()


def build_regional_summaries(
    glyphs: list[PoseDeltaGlyphData],
) -> tuple[RegionalSummaryData, ...]:
    summaries: list[RegionalSummaryData] = []
    for region_id in REGION_ORDER:
        region_glyphs = [glyph for glyph in glyphs if glyph.region_id == region_id]
        if not region_glyphs:
            continue
        magnitudes = [glyph.magnitude for glyph in region_glyphs]
        summaries.append(
            RegionalSummaryData(
                region_id=region_id,
                label=REGION_LABELS[region_id],
                color=REGION_COLORS[region_id],
                vertebra_ids=tuple(glyph.vertebra_id for glyph in region_glyphs),
                average_magnitude=sum(magnitudes) / len(magnitudes),
                peak_magnitude=max(magnitudes),
                total_magnitude=sum(magnitudes),
            )
        )
    return tuple(summaries)


def classify_region(vertebra_id: str) -> str:
    normalized = vertebra_id.upper()
    if normalized == "PELVIS" or normalized.startswith("S"):
        return "pelvis"
    if normalized.startswith("C"):
        return "cervical"
    if normalized.startswith("T"):
        return "thoracic"
    if normalized.startswith("L"):
        return "lumbar"
    return "other"


def summarize_pipeline_runs(manifest: CaseManifest) -> list[str]:
    if not manifest.pipeline_runs:
        return ["No pipeline activity yet"]
    lines: list[str] = []
    for pipeline_run in manifest.pipeline_runs:
        stage_label = pipeline_run.stage.replace("_", " ").title()
        status_label = pipeline_run.status.title()
        lines.append(f"{stage_label}: {status_label}")
    return lines


def build_notes_seed(
    manifest: CaseManifest,
    regional_summaries: tuple[RegionalSummaryData, ...],
    trend_values: dict[str, list[float]],
) -> str:
    diagnosis = manifest.diagnosis or "No diagnosis recorded"
    if not regional_summaries:
        return (
            f"Case summary\n\n"
            f"- Patient: {manifest.patient_name or 'Untitled Case'}\n"
            f"- Diagnosis: {diagnosis}\n"
            f"- Interpretation: no standing-to-supine pose comparison is available yet.\n"
        )
    dominant_region = max(regional_summaries, key=lambda item: item.total_magnitude)
    peak_magnitude = max(trend_values.get("magnitude", []), default=0.0)
    return (
        f"Case summary\n\n"
        f"- Patient: {manifest.patient_name or 'Untitled Case'}\n"
        f"- Diagnosis: {diagnosis}\n"
        f"- Dominant motion region: {dominant_region.label}\n"
        f"- Peak vertebral displacement: {format_distance(peak_magnitude)}\n"
        f"- Interpretation: pelvis-aligned comparison shows the strongest relative motion in the "
        f"{dominant_region.label.lower()} region.\n"
    )


def format_distance(value: float) -> str:
    return f"{value:.1f} mm"
