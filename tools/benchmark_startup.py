from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from spinelab.io.case_store import DEFAULT_DATA_ROOT


def _timed_import(import_statement: str, *, repeats: int) -> dict[str, object]:
    samples: list[float] = []
    for _ in range(max(1, repeats)):
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import time; "
                    "started=time.perf_counter(); "
                    f"{import_statement}; "
                    "elapsed=time.perf_counter()-started; "
                    "print(f'{elapsed:.6f}')"
                ),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        samples.append(float(completed.stdout.strip()))
    return {
        "statement": import_statement,
        "samples_seconds": [round(sample, 6) for sample in samples],
        "best_seconds": round(min(samples), 6),
        "median_seconds": round(sorted(samples)[len(samples) // 2], 6),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark cold import paths for SpineLab startup-sensitive modules."
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=5,
        help="Number of fresh-process timing samples to collect per import.",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_DATA_ROOT / "raw_test_data" / "_benchmarks" / "startup"),
        help="Directory where the benchmark results should be written.",
    )
    args = parser.parse_args()

    run_dir = Path(args.output_root) / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    records = {
        "generated_at": datetime.now().isoformat(),
        "python": sys.executable,
        "repeats": max(1, int(args.repeats)),
        "imports": [
            _timed_import("from spinelab.visualization import ViewportMode", repeats=args.repeats),
            _timed_import("from spinelab.app.main_window import MainWindow", repeats=args.repeats),
        ],
    }

    output_path = run_dir / "startup_imports.json"
    output_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"Wrote startup benchmark results to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
