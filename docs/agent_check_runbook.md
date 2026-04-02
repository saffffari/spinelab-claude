# SpineLab Agent Check Runbook

This document is the canonical runbook for recurring SpineLab validation. It is written for agents that need to execute regular checks on either a hosted CI runner or the local Windows workstation without inventing new automation or silently changing the intended validation surface.

Use this runbook together with [docs/project_brief.md](/D:/claude/spinelab/docs/project_brief.md), [docs/design_system.md](/D:/claude/spinelab/docs/design_system.md), and [docs/code_review.md](/D:/claude/spinelab/docs/code_review.md). The brief defines the product path and non-negotiables, the design system defines viewport and UI interaction constraints, and the code review rubric defines the main regression surface.

## Status Vocabulary

Agents must classify each check using one of the following statuses:

- `pass`: the check ran and met its documented pass criteria.
- `known-failure`: the check failed, but the failure matches the dated baseline recorded in this runbook.
- `regression`: the check failed in a new way, failed with a broader scope than the known baseline, or showed materially worse benchmark behavior than the previous saved run.
- `blocked`: the current target should run the check, but a documented prerequisite is missing.
- `not-applicable`: the current target does not include this check.

Use `blocked` only when the target is correct but the environment is incomplete. Use `not-applicable` when the check is intentionally outside the current target, such as a local-only GUI smoke check on a hosted CI runner.

## Target And Tier Policy

| Tier | Purpose | Target | Cadence | Result Policy |
| --- | --- | --- | --- | --- |
| Tier 1 | Fast correctness gate | both | every branch push, PR, and pre-merge verification | gating |
| Tier 2 | Real shell and `Analyze -> Review` smoke | local-only | daily on the workstation and before UI or pipeline signoff | gating for local signoff, `not-applicable` on CI |
| Tier 3 | Optimization and throughput audit | mixed, mostly local-only | scheduled daily or weekly, and before release candidates | report-only |

## Environment Bootstrap

Run the bootstrap once per fresh environment before executing any check entry.

### CI-Oriented Bootstrap

```powershell
cd D:\claude\spinelab
conda env create -f environment.yml
conda run -n spinelab-claude python -m pip install -e .
```

### Local Workstation Bootstrap

```powershell
cd D:\claude\spinelab
conda run -n spinelab-claude python -m pip install -e .
```

If the app environment needs a full rebuild, follow the setup section in [README.md](/D:/claude/spinelab/README.md) first, then return to this runbook.

## Check Entries

### Check 1. Fast Repo Gate

- Target: `both`
- Cadence: every branch push, PR, pre-merge verification, and before release tagging
- Prerequisites:
  - the repo is available at `D:\claude\spinelab`
  - the `spinelab-claude` environment exists and has `python -m pip install -e .` applied
  - the agent can invoke `conda run` or the local PowerShell wrapper
- Command:
  - Local Windows wrapper:

    ```powershell
    powershell -ExecutionPolicy Bypass -File .\tools\run_repo_checks.ps1
    ```

  - Explicit fallback sequence for CI or wrapper troubleshooting:

    ```powershell
    conda run -n spinelab-claude python tools/check_theme_usage.py
    conda run -n spinelab-claude python -m ruff check .
    conda run -n spinelab-claude python -m mypy src
    conda run -n spinelab-claude python -m pytest -q
    ```

- Pass criteria:
  - `tools/check_theme_usage.py` exits successfully
  - `ruff`, `mypy`, and `pytest -q` each exit successfully
  - no new command bootstrap errors appear
- Blocked criteria:
  - the app environment does not exist
  - `conda` is unavailable
  - the repo cannot be installed in editable mode
- Artifacts produced:
  - console output only unless the caller redirects logs
  - local caches such as `.mypy_cache`, `.pytest_cache`, and `.ruff_cache`
- Escalation guidance:
  - mark the check as `known-failure` only if the failures match the dated baseline below
  - mark the check as `regression` if counts, files, or failure themes expand beyond the known baseline
  - if the wrapper fails before running all tools, rerun the explicit fallback sequence and report both outcomes

#### Baseline As Of 2026-03-26

The repository is green at the current baseline.

- `ruff check .`: pass
- `python -m mypy src`: pass
- `python -m pytest -q`: pass

Agents should treat any new Tier 1 failure as a `regression` unless the failure can be tied to an intentionally unmerged local worktree experiment.

### Check 2. Real App Shell Launch Smoke

- Target: `local-only`
- Cadence: daily on the workstation and before signoff on UI, viewport, shell, or workflow changes
- Prerequisites:
  - the local workstation can display Qt windows
  - the `spinelab-claude` environment is installed
  - the machine exposes a usable hardware OpenGL path
- Command:

  ```powershell
  conda run -n spinelab-claude python -m spinelab.main
  ```

  The equivalent `spinelab` launcher is also acceptable on the workstation.

- Pass criteria:
  - the real `MainWindow` shell launches
  - the app does not fall back to software OpenGL
  - shell chrome, sidebar behavior, and workspace loading occur in the real app shell rather than a standalone `workspace.show()` harness
  - the header status strip and render-backend state do not show an unexpected failure
- Blocked criteria:
  - no interactive desktop session is available
  - the machine lacks hardware OpenGL or cannot initialize the renderer
  - the local workstation does not have the app environment installed
- Artifacts produced:
  - none required
  - optional screenshots or notes if the agent is capturing visual evidence
- Escalation guidance:
  - mark as `blocked` if the workstation cannot provide interactive rendering
  - mark as `regression` for new shell launch failures, software-render fallback, or broken shell grammar

### Check 3. `Analyze -> Review` Product-Path Smoke

- Target: `local-only`
- Cadence: daily on the workstation, before pipeline signoff, and before release candidates
- Prerequisites:
  - a representative saved `.spine` package exists, typically under `E:\data\spinelab\cases`
  - the case package includes the assets needed for the intended validation path
  - the active production segmentation bundle is configured in settings and resolves through the installed runtime model
  - a usable GPU is available for the intended workstation validation path
- Command:
  - launch the real shell through Check 2
  - open a representative saved `.spine` package in the Import workspace
  - execute the real `Analyze` action and follow the production `Analyze -> Review` path through Import, Measurement, and Report
- Pass criteria:
  - Import accepts the case and exposes the real analysis controls
  - `Analyze` completes without an unhandled error dialog
  - Measurement and Report unlock from the updated manifest outputs
  - the transient runtime manifest under `%LOCALAPPDATA%\SpineLab\sessions\<session-id>\runtime\case_manifest.json` records stage runs, requested versus effective device metadata, and stage outputs
  - stage roots under the transient session `analytics/derived/` tree contain the expected `performance-trace.json` files where the current pipeline writes them
  - viewport interaction remains aligned with [docs/design_system.md](/D:/claude/spinelab/docs/design_system.md):
    - middle mouse pans 3D, orthographic, and 2D viewports
    - wheel zooms by default
    - the CT stack keeps wheel-to-slice and `Ctrl` plus wheel zoom
- Blocked criteria:
  - no representative saved `.spine` package is available
  - no GPU is available on the local workstation
  - no active production segmentation bundle is configured
  - the agent cannot operate the real shell
- Artifacts produced:
  - the transient runtime manifest under `%LOCALAPPDATA%\SpineLab\sessions\<session-id>\runtime\case_manifest.json`
  - stage-owned outputs under the transient session `analytics/derived/` tree
  - per-stage `performance-trace.json` files where emitted by the pipeline
- Escalation guidance:
  - do not convert missing GPU, missing case data, or missing production bundle into generic failures; report them as `blocked`
  - mark as `regression` if the real product path no longer reaches Measurement or Report, if metadata is missing from pipeline runs, or if viewport interaction rules drift

### Check 4. Startup Import Benchmark

- Target: `both`
- Cadence: scheduled daily or weekly, and before release candidates
- Prerequisites:
  - the `spinelab-claude` environment is installed
- Command:

  ```powershell
  conda run -n spinelab-claude python .\tools\benchmark_startup.py
  ```

- Pass criteria:
  - the tool exits successfully
  - a new run directory is created under `E:\data\spinelab\raw_test_data\_benchmarks\startup\`
  - the generated `startup_imports.json` is readable
- Blocked criteria:
  - the benchmark output root cannot be created
  - the app environment is unavailable
- Artifacts produced:
  - `E:\data\spinelab\raw_test_data\_benchmarks\startup\<timestamp>\startup_imports.json`
- Escalation guidance:
  - this is report-only
  - compare the newest run to the immediately previous saved run and describe the delta instead of enforcing a hard threshold
  - mark as `regression` only for tool failure or materially worse startup timings without an explained cause

### Check 5. Mesh Benchmark Audit

- Target: `local-only`
- Cadence: scheduled daily or weekly, after mesh-stage changes, and before release candidates
- Prerequisites:
  - saved `.spine` cases or exported transient cases with existing segmentation contracts are available
  - the app environment is installed
- Command:

  ```powershell
  conda run -n spinelab-claude python .\tools\benchmark_mesh_pipeline.py
  ```

  Or target a specific case or segmentation contract:

  ```powershell
  conda run -n spinelab-claude python .\tools\benchmark_mesh_pipeline.py E:\data\spinelab\cases\<case-id>\analytics\derived\segmentation\segmentation.json
  ```

- Pass criteria:
  - the benchmark exits successfully
  - a new run directory is created under `E:\data\spinelab\raw_test_data\_benchmarks\mesh_pipeline\`
  - the benchmark summary files are readable
- Blocked criteria:
  - no segmentation contracts are available under the data root
  - the app environment is unavailable
- Artifacts produced:
  - the benchmark run directory under `E:\data\spinelab\raw_test_data\_benchmarks\mesh_pipeline\`
  - the JSON summary and Markdown summary written by the harness
- Escalation guidance:
  - this is report-only
  - compare the newest run to the previous saved run and summarize runtime, Dice, and QC-pass deltas
  - mark as `regression` for tool failure or materially worse benchmark behavior, not for small natural variance

### Check 6. Pipeline Timing And Trace Audit

- Target: `local-only`
- Cadence: scheduled daily or weekly, after pipeline-stage changes, and before release candidates
- Prerequisites:
  - at least one analyzed transient session exists while the app is open
  - the session contains `%LOCALAPPDATA%\SpineLab\sessions\<session-id>\runtime\case_manifest.json`
- Command:
  - inspect `%LOCALAPPDATA%\SpineLab\sessions\<session-id>\runtime\case_manifest.json`
  - inspect each stage root under `%LOCALAPPDATA%\SpineLab\sessions\<session-id>\workspace\analytics\derived\` for `performance-trace.json`
- Pass criteria:
  - stage runs record requested versus effective device metadata
  - stage runs record inputs and outputs
  - `performance-trace.json` files exist where the pipeline currently emits them
  - no stage unexpectedly loses provenance or runtime metadata
- Blocked criteria:
  - no analyzed case is available
  - expected manifest outputs are absent because the product-path smoke has not yet been run
- Artifacts produced:
  - no new artifacts; this is an audit of existing case outputs
- Escalation guidance:
  - this is report-only
  - compare the latest analyzed case against the previous reference case and describe any timing or metadata regressions

### Check 7. Optional Local nnU-Net Inference Smoke

- Target: `local-only`
- Cadence: scheduled only, after segmentation-sidecar changes, or before release candidates that touch production segmentation
- Prerequisites:
  - a CUDA-capable GPU is available
  - the `spinelab-nnunet` environment is installed
  - CADS pretrained model checkpoints are installed under `E:\data\spinelab\raw_test_data\models\segmentation\`
  - raw test data exists under `E:\data\spinelab\raw_test_data`
- Command: run Analyze on a test case through the GUI or use `tools/prepare_cads_nnunet.py` for standalone inference.

- Pass criteria:
  - the wrapper launches the dedicated Windows nnU-Net environment
  - a prediction job directory is created under `E:\data\spinelab\raw_test_data\outputs`
  - the run manifest is written and the prediction outputs are materially usable for smoke evaluation
- Blocked criteria:
  - no GPU is available
  - the dedicated nnU-Net environment is unavailable
  - no checkpoint is installed at the configured results root
  - no raw test data is present
- Artifacts produced:
  - a job folder under `E:\data\spinelab\raw_test_data\outputs\`
  - `run_manifest.json` and prediction outputs from the helper
- Escalation guidance:
  - this is report-only
  - use it to detect broken segmentation-sidecar wiring or throughput regressions
  - do not require a hard latency threshold in the runbook; compare with the previous saved smoke record instead

## Production Segmentation Bundle Prerequisite

The current production segmentation path requires an active installed bundle. The repository exposes the bundle registry and installation logic in code under [src/spinelab/segmentation/bundles.py](/D:/claude/spinelab/src/spinelab/segmentation/bundles.py), including `SegmentationBundleRegistry`. It also ships a checked-in helper at [tools/install_cads_bundles.py](/D:/claude/spinelab/tools/install_cads_bundles.py) for importing CADS pretrained model zips and activating a composite bundle.

If the workstation intends to run Check 3 and no production bundle is active, resolve that prerequisite out of band before rerunning the smoke path. The helper entrypoint is:

```powershell
conda run -n spinelab-claude python .\tools\install_cads_bundles.py --zips-dir <path-to-model-zips> --activate skeleton
```

If a check requires a production bundle and none is configured, classify the check as `blocked` and report that the prerequisite gap is operational, not a newly discovered product failure.

## CI-Like Versus Workstation Interpretation

Use the following interpretation rules when executing this runbook:

- On a hosted CI runner without GPU, local case data, or an interactive desktop session:
  - run Tier 1
  - run Check 4 if the environment supports it
  - mark Tier 2 and local-only Tier 3 checks as `not-applicable`
- On the local Windows workstation without a required local prerequisite:
  - mark the affected local check as `blocked`
  - continue with the remaining checks instead of collapsing the entire report
- On the local Windows workstation with the required prerequisites:
  - run all applicable tiers
  - treat Tier 1 and Tier 2 as gating for signoff
  - keep Tier 3 report-only

## Agent Report Template

Agents should end each run with a compact report in the following structure.

```markdown
# SpineLab Check Report

Date: YYYY-MM-DD
Target: ci | local-workstation
Repo: D:\claude\spinelab
Environment:
- Python env(s) used:
- GPU:
- Data root availability:
- Production segmentation bundle availability:

## Commands Run
- `...`
- `...`

## Results
- Tier 1 Fast Repo Gate: `pass | known-failure | regression | blocked | not-applicable`
- Tier 2 Real App Shell Launch Smoke: `...`
- Tier 2 Analyze -> Review Product-Path Smoke: `...`
- Tier 3 Startup Import Benchmark: `...`
- Tier 3 Mesh Benchmark Audit: `...`
- Tier 3 Pipeline Timing And Trace Audit: `...`
- Tier 3 Optional Local nnU-Net Inference Smoke: `...`

## Known Baseline Match
- Describe whether the current `ruff`, `mypy`, and `pytest` failures match the `2026-03-26` baseline exactly.

## Regressions
- List new failures, widened failure scope, or materially worse benchmark deltas.

## Blocked Prerequisites
- List each missing prerequisite separately.

## Artifacts
- List benchmark directories, manifests, traces, screenshots, or output folders created or reviewed.

## Recommended Follow-Ups
- List the highest-value next actions only.
```

Keep the report concise. The primary goal is to let another engineer distinguish baseline debt from new regressions without rereading raw logs.
