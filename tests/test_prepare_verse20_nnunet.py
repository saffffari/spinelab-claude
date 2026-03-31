from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import SimpleITK as sitk


def load_tool_module(module_path: Path, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def prepare_module() -> ModuleType:
    module_path = Path(__file__).resolve().parents[1] / "tools" / "prepare_verse20_nnunet.py"
    return load_tool_module(module_path, "prepare_verse20_nnunet_test")


def write_image(path: Path, *, label: int | None = None) -> None:
    if label is None:
        array = np.arange(8, dtype=np.int16).reshape((2, 2, 2))
    else:
        array = np.zeros((2, 2, 2), dtype=np.uint8)
        array[0, 0, 0] = label
    image = sitk.GetImageFromArray(array)
    image.SetSpacing((1.0, 1.0, 1.0))
    image.SetOrigin((0.0, 0.0, 0.0))
    image.SetDirection((1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0))
    sitk.WriteImage(image, str(path), useCompression=True)


def build_verse_case(verse_root: Path, split_name: str, subject_id: str, case_id: str) -> None:
    split_root = verse_root / {
        "training": "01_training",
        "validation": "02_validation",
        "test": "03_test",
    }[split_name]
    raw_dir = split_root / "rawdata" / subject_id
    derivatives_dir = split_root / "derivatives" / subject_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    derivatives_dir.mkdir(parents=True, exist_ok=True)

    image_path = raw_dir / f"{case_id}_ct.nii.gz"
    label_path = derivatives_dir / f"{case_id}_seg-vert_msk.nii.gz"
    centroid_path = derivatives_dir / f"{case_id}_seg-subreg_ctd.json"
    preview_path = derivatives_dir / f"{case_id}_seg-vert_snp.png"

    write_image(image_path)
    write_image(label_path, label=1)
    centroid_path.write_text(json.dumps([{"label": 1, "coord": [0.0, 0.0, 0.0]}]), encoding="utf-8")
    preview_path.write_bytes(b"preview")


def test_eval_only_rebuilds_holdout_exports_without_touching_training_dataset(
    tmp_path: Path,
) -> None:
    module = prepare_module()
    verse_root = tmp_path / "verse"
    output_root = tmp_path / "nnunet_raw"
    dataset_dir = output_root / "Dataset321_VERSE20Vertebrae"
    images_tr = dataset_dir / "imagesTr"
    labels_tr = dataset_dir / "labelsTr"
    images_tr.mkdir(parents=True)
    labels_tr.mkdir(parents=True)
    sentinel_image = images_tr / "sentinel.txt"
    sentinel_label = labels_tr / "sentinel.txt"
    sentinel_image.write_text("keep-image", encoding="utf-8")
    sentinel_label.write_text("keep-label", encoding="utf-8")

    build_verse_case(verse_root, "training", "sub-verse001", "sub-verse001_dir-ax")
    build_verse_case(verse_root, "validation", "sub-verse101", "sub-verse101_dir-ax")
    build_verse_case(verse_root, "test", "sub-verse201", "sub-verse201_dir-ax")

    module.main(
        [
            "--verse-root",
            str(verse_root),
            "--output-root",
            str(output_root),
            "--dataset-id",
            "321",
            "--dataset-name",
            "VERSE20Vertebrae",
            "--eval-only",
        ]
    )

    assert sentinel_image.read_text(encoding="utf-8") == "keep-image"
    assert sentinel_label.read_text(encoding="utf-8") == "keep-label"
    validation_root = output_root / "eval" / "official_validation"
    test_root = output_root / "eval" / "official_test"
    assert (validation_root / "images" / "sub-verse101_dir-ax_0000.nii.gz").exists()
    assert (validation_root / "labels" / "sub-verse101_dir-ax.nii.gz").exists()
    assert (validation_root / "centroids" / "sub-verse101_dir-ax_seg-subreg_ctd.json").exists()
    assert (validation_root / "previews" / "sub-verse101_dir-ax_seg-vert_snp.png").exists()
    assert (test_root / "images" / "sub-verse201_dir-ax_0000.nii.gz").exists()
