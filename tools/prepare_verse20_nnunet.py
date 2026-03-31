from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import SimpleITK as sitk
from nnunetv2.dataset_conversion.generate_dataset_json import generate_dataset_json

NATIVE_VERTEBRA_LABELS: dict[str, int] = {
    "background": 0,
    "C1": 1,
    "C2": 2,
    "C3": 3,
    "C4": 4,
    "C5": 5,
    "C6": 6,
    "C7": 7,
    "T1": 8,
    "T2": 9,
    "T3": 10,
    "T4": 11,
    "T5": 12,
    "T6": 13,
    "T7": 14,
    "T8": 15,
    "T9": 16,
    "T10": 17,
    "T11": 18,
    "T12": 19,
    "L1": 20,
    "L2": 21,
    "L3": 22,
    "L4": 23,
    "L5": 24,
    "L6": 25,
    "T13": 28,
}

NNUNET_VERTEBRA_LABELS: dict[str, int] = {
    "background": 0,
    "C1": 1,
    "C2": 2,
    "C3": 3,
    "C4": 4,
    "C5": 5,
    "C6": 6,
    "C7": 7,
    "T1": 8,
    "T2": 9,
    "T3": 10,
    "T4": 11,
    "T5": 12,
    "T6": 13,
    "T7": 14,
    "T8": 15,
    "T9": 16,
    "T10": 17,
    "T11": 18,
    "T12": 19,
    "L1": 20,
    "L2": 21,
    "L3": 22,
    "L4": 23,
    "L5": 24,
    "L6": 25,
    "T13": 26,
}

NATIVE_TO_NNUNET_LABELS: dict[int, int] = {
    native_label: NNUNET_VERTEBRA_LABELS[name]
    for name, native_label in NATIVE_VERTEBRA_LABELS.items()
}

SPLIT_DIRS = {
    "training": "01_training",
    "validation": "02_validation",
    "test": "03_test",
}


@dataclass(frozen=True, slots=True)
class VerseCase:
    split_name: str
    subject_id: str
    case_id: str
    image_path: Path
    label_path: Path
    centroid_path: Path
    preview_path: Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert the VERSe2020 subject-based release into an nnU-Net v2 dataset.",
    )
    parser.add_argument("--verse-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--dataset-id", type=int, default=321)
    parser.add_argument("--dataset-name", default="VERSE20Vertebrae")
    parser.add_argument(
        "--link-mode",
        choices=("copy", "symlink"),
        default="copy",
        help="Use symlink on Linux/Lambda to avoid duplicating NIfTI volumes.",
    )
    parser.add_argument(
        "--merge-validation-into-training",
        action="store_true",
        help="Append 02_validation cases into imagesTr/labelsTr once the baseline is stable.",
    )
    parser.add_argument(
        "--skip-eval-exports",
        action="store_true",
        help=(
            "Skip exporting official validation/test holdout files under output_root/eval. "
            "Useful when the immediate goal is to start nnU-Net training as fast as possible."
        ),
    )
    parser.add_argument(
        "--eval-only",
        action="store_true",
        help=(
            "Rebuild only output_root/eval/official_validation and output_root/eval/official_test "
            "without touching imagesTr, labelsTr, or preprocessing inputs."
        ),
    )
    return parser.parse_args(argv)


def discover_cases(verse_root: Path, split_name: str, *, required: bool = True) -> list[VerseCase]:
    split_root = verse_root / SPLIT_DIRS[split_name]
    raw_root = split_root / "rawdata"
    derivatives_root = split_root / "derivatives"
    if not raw_root.exists() or not derivatives_root.exists():
        if required:
            raise FileNotFoundError(
                f"Missing VERSe split directories for {split_name}: {raw_root} / {derivatives_root}"
            )
        return []
    cases: list[VerseCase] = []
    for subject_dir in sorted(path for path in raw_root.iterdir() if path.is_dir()):
        image_candidates = sorted(subject_dir.glob("*_ct.nii.gz"))
        if len(image_candidates) != 1:
            raise RuntimeError(
                f"Expected exactly one CT volume in {subject_dir}, found {len(image_candidates)}."
            )
        image_path = image_candidates[0]
        case_id = image_path.name.removesuffix(".nii.gz").removesuffix("_ct")
        derivatives_dir = derivatives_root / subject_dir.name
        label_path = derivatives_dir / image_path.name.replace(
            "_ct.nii.gz",
            "_seg-vert_msk.nii.gz",
        )
        centroid_path = derivatives_dir / image_path.name.replace(
            "_ct.nii.gz",
            "_seg-subreg_ctd.json",
        )
        preview_path = derivatives_dir / image_path.name.replace(
            "_ct.nii.gz",
            "_seg-vert_snp.png",
        )
        required_paths = (label_path, centroid_path, preview_path)
        missing_paths = [str(path) for path in required_paths if not path.exists()]
        if missing_paths:
            print(
                "Skipping VERSe case with incomplete derivatives:\n"
                f"  split={split_name}\n"
                f"  subject={subject_dir.name}\n"
                f"  missing={missing_paths}",
                file=sys.stderr,
            )
            continue
        cases.append(
            VerseCase(
                split_name=split_name,
                subject_id=subject_dir.name,
                case_id=case_id,
                image_path=image_path,
                label_path=label_path,
                centroid_path=centroid_path,
                preview_path=preview_path,
            )
        )
    return cases


def ensure_empty_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def ensure_existing_training_dataset(dataset_dir: Path) -> None:
    images_tr = dataset_dir / "imagesTr"
    labels_tr = dataset_dir / "labelsTr"
    if not images_tr.exists() or not labels_tr.exists():
        raise FileNotFoundError(
            "Expected an existing nnU-Net training dataset at "
            f"{dataset_dir}. Run a full export before using --eval-only."
        )


def link_or_copy(source: Path, destination: Path, link_mode: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        destination.unlink()
    if link_mode == "symlink":
        os.symlink(source, destination)
        return
    shutil.copy2(source, destination)


def remap_segmentation_labels(source: Path, destination: Path, image_reference_path: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    segmentation = sitk.ReadImage(str(source))
    image_reference = sitk.ReadImage(str(image_reference_path))
    if segmentation.GetSize() != image_reference.GetSize():
        raise ValueError(
            "Segmentation/image size mismatch for "
            f"{source} vs {image_reference_path}: "
            f"{segmentation.GetSize()} != {image_reference.GetSize()}"
        )

    data = sitk.GetArrayFromImage(segmentation)
    unique_labels = {int(value) for value in np.unique(data)}
    unexpected = sorted(unique_labels - set(NATIVE_TO_NNUNET_LABELS))
    if unexpected:
        raise ValueError(f"Unexpected labels in {source}: {unexpected}")

    remapped = np.zeros(data.shape, dtype=np.uint8)
    for native_label, training_label in NATIVE_TO_NNUNET_LABELS.items():
        remapped[data == native_label] = training_label

    remapped_image = sitk.GetImageFromArray(remapped, isVector=False)
    remapped_image.CopyInformation(image_reference)
    sitk.WriteImage(remapped_image, str(destination), useCompression=True)


def remap_centroid_labels(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.loads(source.read_text(encoding="utf-8"))
    remapped_payload: list[object] = []
    for item in payload:
        if isinstance(item, dict) and "label" in item:
            native_label = int(item["label"])
            if native_label not in NATIVE_TO_NNUNET_LABELS:
                raise ValueError(f"Unexpected centroid label in {source}: {native_label}")
            remapped_item = dict(item)
            remapped_item["label"] = NATIVE_TO_NNUNET_LABELS[native_label]
            remapped_payload.append(remapped_item)
        else:
            remapped_payload.append(item)
    destination.write_text(json.dumps(remapped_payload, indent=2), encoding="utf-8")


def export_training_cases(cases: list[VerseCase], dataset_dir: Path, link_mode: str) -> None:
    images_tr = dataset_dir / "imagesTr"
    labels_tr = dataset_dir / "labelsTr"
    ensure_empty_dir(images_tr)
    ensure_empty_dir(labels_tr)
    for case in cases:
        link_or_copy(case.image_path, images_tr / f"{case.case_id}_0000.nii.gz", link_mode)
        remap_segmentation_labels(
            case.label_path,
            labels_tr / f"{case.case_id}.nii.gz",
            case.image_path,
        )


def export_eval_cases(
    cases: list[VerseCase],
    eval_root: Path,
    link_mode: str,
) -> None:
    images_dir = eval_root / "images"
    labels_dir = eval_root / "labels"
    centroids_dir = eval_root / "centroids"
    previews_dir = eval_root / "previews"
    for directory in (images_dir, labels_dir, centroids_dir, previews_dir):
        ensure_empty_dir(directory)
    for case in cases:
        link_or_copy(case.image_path, images_dir / f"{case.case_id}_0000.nii.gz", link_mode)
        remap_segmentation_labels(
            case.label_path,
            labels_dir / f"{case.case_id}.nii.gz",
            case.image_path,
        )
        remap_centroid_labels(case.centroid_path, centroids_dir / case.centroid_path.name)
        link_or_copy(case.preview_path, previews_dir / case.preview_path.name, link_mode)


def write_manifest(
    output_root: Path,
    dataset_dir: Path,
    training_cases: list[VerseCase],
    validation_cases: list[VerseCase],
    test_cases: list[VerseCase],
) -> None:
    manifest = {
        "dataset_dir": str(dataset_dir),
        "training_cases": [asdict(case) for case in training_cases],
        "official_validation_cases": [asdict(case) for case in validation_cases],
        "official_test_cases": [asdict(case) for case in test_cases],
        "label_policy": {
            "description": (
                "Preserve native VERSe vertebra labels in the manifest, but remap them "
                "to consecutive nnU-Net training labels."
            ),
            "native_labels": NATIVE_VERTEBRA_LABELS,
            "nnunet_labels": NNUNET_VERTEBRA_LABELS,
            "native_to_nnunet": NATIVE_TO_NNUNET_LABELS,
        },
    }
    manifest_path = output_root / "verse20_nnunet_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    verse_root = args.verse_root.resolve()
    output_root = args.output_root.resolve()
    dataset_dir = output_root / f"Dataset{args.dataset_id:03d}_{args.dataset_name}"
    eval_root = output_root / "eval"

    if args.eval_only and args.merge_validation_into_training:
        raise ValueError("--eval-only cannot be combined with --merge-validation-into-training")
    if args.eval_only and args.skip_eval_exports:
        raise ValueError("--eval-only cannot be combined with --skip-eval-exports")

    training_cases = discover_cases(verse_root, "training")
    validation_cases = discover_cases(verse_root, "validation", required=False)
    test_cases = discover_cases(verse_root, "test", required=False)

    training_export = list(training_cases)
    if args.merge_validation_into_training:
        training_export.extend(validation_cases)

    if args.eval_only:
        ensure_existing_training_dataset(dataset_dir)
        ensure_empty_dir(eval_root)
        export_eval_cases(validation_cases, eval_root / "official_validation", args.link_mode)
        export_eval_cases(test_cases, eval_root / "official_test", args.link_mode)
    else:
        ensure_empty_dir(dataset_dir)
        if args.skip_eval_exports:
            eval_root.mkdir(parents=True, exist_ok=True)
        else:
            ensure_empty_dir(eval_root)
        export_training_cases(training_export, dataset_dir, args.link_mode)
        if not args.skip_eval_exports:
            export_eval_cases(validation_cases, eval_root / "official_validation", args.link_mode)
            export_eval_cases(test_cases, eval_root / "official_test", args.link_mode)

        generate_dataset_json(
            str(dataset_dir),
            channel_names={0: "CT"},
            labels=dict(NNUNET_VERTEBRA_LABELS),
            num_training_cases=len(training_export),
            file_ending=".nii.gz",
            dataset_name=args.dataset_name,
            reference="VERSe2020 subject-based release",
            release="2020",
            license="CC BY-SA 4.0",
            description=(
                "SpineLab VERSe2020 vertebra segmentation baseline. "
                "Official validation and test are exported outside imagesTr/labelsTr."
            ),
            overwrite_image_reader_writer="SimpleITKIO",
            spinelab_dataset_manifest="verse20_nnunet_manifest.json",
        )
    write_manifest(output_root, dataset_dir, training_export, validation_cases, test_cases)

    if args.eval_only:
        print(f"Rebuilt eval holdout exports under: {eval_root}")
        print(f"Official validation holdout files: {len(validation_cases)}")
        print(f"Official test holdout files: {len(test_cases)}")
        print("Did not touch imagesTr, labelsTr, planning, or preprocessing inputs.")
    else:
        print(f"Prepared nnU-Net dataset at: {dataset_dir}")
        print(f"Training cases exported: {len(training_export)}")
        print(f"Official validation holdout metadata: {len(validation_cases)}")
        print(f"Official test holdout metadata: {len(test_cases)}")
        if args.skip_eval_exports:
            print("Skipped exporting eval holdout files under output_root/eval for this run.")
        print(
            "Next: set nnUNet_raw/nnUNet_preprocessed/nnUNet_results and run "
            "fingerprint -> plan_experiment -> preprocess -> train."
        )


if __name__ == "__main__":
    main()
