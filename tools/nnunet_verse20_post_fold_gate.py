from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

FATAL_LOG_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"traceback", re.IGNORECASE), "Traceback"),
    (re.compile(r"runtimeerror", re.IGNORECASE), "RuntimeError"),
    (re.compile(r"(cuda )?out of memory", re.IGNORECASE), "Out of memory"),
    (re.compile(r"\bnan\b", re.IGNORECASE), "NaN"),
)
EPOCH_PATTERN = re.compile(r"Epoch\s+(\d+)")
EMA_DICE_PATTERN = re.compile(r"New best EMA pseudo Dice[:\s]+([0-9]*\.?[0-9]+)")


@dataclass(slots=True)
class LaunchMetadata:
    fold: int
    tmux_session_name: str
    fold_dir: str


@dataclass(slots=True)
class GateSummary:
    status: str
    passed: bool
    generated_at_utc: str
    fold_dir: str
    minimum_foreground_dice: float
    checkpoint_final_path: str | None
    checkpoint_best_path: str | None
    validation_summary_path: str | None
    training_log_path: str | None
    last_epoch_seen: int | None
    max_ema_pseudo_dice: float | None
    foreground_mean_dice: float | None
    fatal_log_markers: list[str]
    reasons: list[str]
    launch: LaunchMetadata | None = None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gate a completed nnU-Net fold before launching the next fold.",
    )
    parser.add_argument("--fold-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--minimum-foreground-dice", type=float, default=0.70)
    parser.add_argument("--launch-fold", type=int)
    parser.add_argument("--launch-session")
    parser.add_argument("--launch-fold-dir", type=Path)
    return parser.parse_args(argv)


def find_training_log(fold_dir: Path) -> Path | None:
    candidates = sorted(fold_dir.glob("training_log*.txt"))
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def parse_training_log(log_path: Path) -> tuple[int | None, float | None, list[str]]:
    last_epoch_seen: int | None = None
    max_ema_pseudo_dice: float | None = None
    fatal_markers: list[str] = []

    for raw_line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        epoch_match = EPOCH_PATTERN.search(raw_line)
        if epoch_match:
            last_epoch_seen = int(epoch_match.group(1))
        ema_match = EMA_DICE_PATTERN.search(raw_line)
        if ema_match:
            score = float(ema_match.group(1))
            if max_ema_pseudo_dice is None or score > max_ema_pseudo_dice:
                max_ema_pseudo_dice = score
        for pattern, marker_name in FATAL_LOG_PATTERNS:
            if pattern.search(raw_line) and marker_name not in fatal_markers:
                fatal_markers.append(marker_name)

    return last_epoch_seen, max_ema_pseudo_dice, fatal_markers


def load_foreground_mean_dice(summary_path: Path) -> float:
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    try:
        return float(payload["foreground_mean"]["Dice"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"Validation summary at {summary_path} does not contain foreground_mean.Dice"
        ) from exc


def evaluate_fold(
    fold_dir: Path,
    minimum_foreground_dice: float,
    launch: LaunchMetadata | None = None,
) -> GateSummary:
    reasons: list[str] = []
    checkpoint_final = fold_dir / "checkpoint_final.pth"
    checkpoint_best = fold_dir / "checkpoint_best.pth"
    validation_summary = fold_dir / "validation" / "summary.json"
    training_log = find_training_log(fold_dir)
    last_epoch_seen: int | None = None
    max_ema_pseudo_dice: float | None = None
    foreground_mean_dice: float | None = None
    fatal_markers: list[str] = []

    if not checkpoint_final.exists():
        reasons.append(f"Missing checkpoint_final.pth at {checkpoint_final}")
    if not checkpoint_best.exists():
        reasons.append(f"Missing checkpoint_best.pth at {checkpoint_best}")
    if training_log is None:
        reasons.append(f"Missing training log under {fold_dir}")
    else:
        last_epoch_seen, max_ema_pseudo_dice, fatal_markers = parse_training_log(training_log)
        if fatal_markers:
            reasons.append(
                "Training log contains fatal markers: " + ", ".join(sorted(fatal_markers))
            )
    if not validation_summary.exists():
        reasons.append(f"Missing validation summary at {validation_summary}")
    else:
        try:
            foreground_mean_dice = load_foreground_mean_dice(validation_summary)
        except ValueError as exc:
            reasons.append(str(exc))
        else:
            if foreground_mean_dice < minimum_foreground_dice:
                reasons.append(
                    "foreground_mean.Dice "
                    f"{foreground_mean_dice:.4f} is below gate {minimum_foreground_dice:.4f}"
                )

    passed = not reasons
    return GateSummary(
        status="pass" if passed else "fail",
        passed=passed,
        generated_at_utc=datetime.now(UTC).isoformat(timespec="seconds"),
        fold_dir=str(fold_dir),
        minimum_foreground_dice=minimum_foreground_dice,
        checkpoint_final_path=str(checkpoint_final) if checkpoint_final.exists() else None,
        checkpoint_best_path=str(checkpoint_best) if checkpoint_best.exists() else None,
        validation_summary_path=str(validation_summary) if validation_summary.exists() else None,
        training_log_path=str(training_log) if training_log is not None else None,
        last_epoch_seen=last_epoch_seen,
        max_ema_pseudo_dice=max_ema_pseudo_dice,
        foreground_mean_dice=foreground_mean_dice,
        fatal_log_markers=fatal_markers,
        reasons=reasons,
        launch=launch,
    )


def render_markdown(summary: GateSummary) -> str:
    lines = [
        f"# Fold gate summary: {Path(summary.fold_dir).name}",
        "",
        f"- Status: `{summary.status}`",
        f"- Generated: `{summary.generated_at_utc}`",
        f"- Fold directory: `{summary.fold_dir}`",
        f"- Minimum foreground Dice: `{summary.minimum_foreground_dice:.4f}`",
        f"- Last epoch seen: `{summary.last_epoch_seen}`",
        f"- Max EMA pseudo Dice: `{summary.max_ema_pseudo_dice}`",
        f"- Foreground mean Dice: `{summary.foreground_mean_dice}`",
        f"- Checkpoint final: `{summary.checkpoint_final_path}`",
        f"- Checkpoint best: `{summary.checkpoint_best_path}`",
        f"- Validation summary: `{summary.validation_summary_path}`",
        f"- Training log: `{summary.training_log_path}`",
    ]
    if summary.fatal_log_markers:
        lines.append(f"- Fatal log markers: `{', '.join(summary.fatal_log_markers)}`")
    if summary.launch is not None:
        lines.extend(
            [
                "",
                "## Next fold launch",
                "",
                f"- Fold: `{summary.launch.fold}`",
                f"- tmux session: `{summary.launch.tmux_session_name}`",
                f"- Fold directory: `{summary.launch.fold_dir}`",
            ]
        )
    if summary.reasons:
        lines.extend(["", "## Gate reasons", ""])
        lines.extend(f"- {reason}" for reason in summary.reasons)
    else:
        lines.extend(["", "## Gate reasons", "", "- Gate passed."])
    return "\n".join(lines) + "\n"


def write_summary(summary: GateSummary, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    fold_name = Path(summary.fold_dir).name
    json_path = output_dir / f"{fold_name}_gate_summary.json"
    markdown_path = output_dir / f"{fold_name}_gate_summary.md"
    payload = asdict(summary)
    if summary.launch is not None:
        payload["launch"] = asdict(summary.launch)
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown(summary), encoding="utf-8")
    return json_path, markdown_path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    launch_metadata: LaunchMetadata | None = None
    launch_metadata_args = (
        args.launch_fold,
        args.launch_session,
        args.launch_fold_dir,
    )
    if any(value is not None for value in launch_metadata_args):
        if None in (args.launch_fold, args.launch_session, args.launch_fold_dir):
            print(
                "launch metadata requires --launch-fold, --launch-session, and "
                "--launch-fold-dir together",
                file=sys.stderr,
            )
            return 2
        launch_metadata = LaunchMetadata(
            fold=args.launch_fold,
            tmux_session_name=args.launch_session,
            fold_dir=str(args.launch_fold_dir),
        )

    fold_dir = args.fold_dir.resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else (fold_dir / "post_fold").resolve()
    )
    summary = evaluate_fold(
        fold_dir=fold_dir,
        minimum_foreground_dice=args.minimum_foreground_dice,
        launch=launch_metadata,
    )
    write_summary(summary, output_dir)
    return 0 if summary.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
