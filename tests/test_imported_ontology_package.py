from __future__ import annotations

from pathlib import Path

import yaml

EXPECTED_PER_VERTEBRA_CODES = (
    "SEP",
    "IEP",
    "ASC",
    "PSC",
    "AIC",
    "PIC",
    "SEM",
    "IEM",
    "VBC",
    "PWL",
    "MSP",
    "MCP",
)

EXPECTED_PELVIC_SACRAL_CODES = (
    "S1SEP",
    "S1MID",
    "S1PSC",
    "FH-L",
    "FH-R",
    "HAX",
    "SACC",
)

EXPECTED_GLOBAL_SPINE_CODES = (
    "C7C",
    "EV-U",
    "EV-L",
    "AV",
    "NV",
    "SV",
    "AC",
)

EXPECTED_MEASUREMENTS = (
    "DISC_HEIGHT_MIDPOINT",
    "DISC_HEIGHT_ANTERIOR",
    "DISC_HEIGHT_POSTERIOR",
    "DISC_SPACE_ANGLE",
    "SPONDYLOLISTHESIS_RETROLISTHESIS",
    "PELVIC_INCIDENCE",
    "PELVIC_TILT",
    "SACRAL_SLOPE",
    "LUMBAR_LORDOSIS",
    "SEGMENTAL_LORDOSIS",
    "APEX_OF_LORDOSIS",
    "THORACIC_KYPHOSIS",
    "TL_JUNCTION_KYPHOSIS",
    "SVA",
    "CORONAL_BALANCE_C7_CSVL",
    "COBB_ANGLE",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ontology_path() -> Path:
    return _repo_root() / "docs" / "ontology" / "spinelab_vertebral_labeling_ontology.yaml"


def _load_ontology() -> dict[str, object]:
    with _ontology_path().open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    assert isinstance(payload, dict)
    return payload


def test_single_file_ontology_package_is_frozen() -> None:
    ontology_dir = _repo_root() / "docs" / "ontology"
    files = sorted(path.name for path in ontology_dir.iterdir() if path.is_file())

    assert files == ["spinelab_vertebral_labeling_ontology.yaml"]


def test_imported_ontology_metadata_is_approval_gated() -> None:
    payload = _load_ontology()

    assert payload["schema_version"] == "1.0.0"
    assert payload["canonical_source"] is True

    edit_policy = payload["edit_policy"]
    assert isinstance(edit_policy, dict)
    assert edit_policy["requires_explicit_user_approval"] is True

    implementation_scope = payload["implementation_scope"]
    assert isinstance(implementation_scope, dict)
    assert implementation_scope["ontology_is_growth_envelope"] is True
    assert implementation_scope["full_metric_list_is_not_implementation_commitment"] is True

    runtime_boundary = payload["runtime_boundary"]
    assert isinstance(runtime_boundary, dict)
    assert runtime_boundary["runtime_source_of_truth"] == "src/spinelab/ontology/"
    assert runtime_boundary["explicit_approval_required_for_reconciliation"] is True


def test_imported_ontology_landmark_codes_are_frozen() -> None:
    payload = _load_ontology()
    landmarks = payload["landmarks"]
    assert isinstance(landmarks, dict)

    per_vertebra_core = landmarks["per_vertebra_core"]
    pelvic_sacral = landmarks["pelvic_sacral"]
    global_spine = landmarks["global_spine"]

    assert tuple(entry["code"] for entry in per_vertebra_core) == EXPECTED_PER_VERTEBRA_CODES
    assert tuple(entry["code"] for entry in pelvic_sacral) == EXPECTED_PELVIC_SACRAL_CODES
    assert tuple(entry["code"] for entry in global_spine) == EXPECTED_GLOBAL_SPINE_CODES


def test_imported_measurement_dependency_matrix_is_embedded_and_frozen() -> None:
    payload = _load_ontology()
    matrix = payload["measurement_dependency_matrix"]
    assert isinstance(matrix, list)

    assert tuple(entry["measurement_name"] for entry in matrix) == EXPECTED_MEASUREMENTS
    for entry in matrix:
        assert tuple(entry.keys()) == (
            "measurement_name",
            "category",
            "required_landmarks",
            "optional_helpful",
            "output_type",
            "formula_summary",
            "poc_priority",
        )


def test_imported_ontology_notes_explicitly_allow_future_growth() -> None:
    payload = _load_ontology()
    implementation_scope = payload["implementation_scope"]
    assert isinstance(implementation_scope, dict)

    notes = implementation_scope["notes"]
    assert isinstance(notes, list)
    assert any("Not every listed metric" in note for note in notes)
    assert any("future room for growth" in note for note in notes)


def test_repo_docs_mark_imported_ontology_as_approval_gated() -> None:
    doc_paths = (
        _repo_root() / "AGENTS.md",
        _repo_root() / "README.md",
        _repo_root() / "docs" / "data_contracts.md",
        _repo_root() / "docs" / "measurement_spec.md",
        _repo_root() / "docs" / "project_brief.md",
    )

    for path in doc_paths:
        text = path.read_text(encoding="utf-8")
        assert "spinelab_vertebral_labeling_ontology.yaml" in text, str(path)
        assert "explicit user approval" in text.lower(), str(path)
