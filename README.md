# SpineLab 0.2

SpineLab 0.2 is the native Windows rebuild of the SpineLab desktop review workbench. The current Electron/React prototype is frozen under `prototypes/electron-ui/` as a visual and workflow baseline. The real product lives under `src/spinelab/` and uses `PySide6` for the shell and `PyVista` for 3D review viewports.

The repo now includes a local-first backend foundation under `src/spinelab/pipeline/`. The desktop app remains a clean Python 3.12 runtime, while CUDA-capable research tools are planned as isolated sidecar environments declared under `envs/`.

Current repo state:

- the native desktop shell, workspaces, renderer probe, and GPU-backed viewport stack are in place
- import, measurement, and report workflows are stable enough for UI iteration and artifact review
- `src/spinelab/pipeline/` now uses a dependency-aware in-app stage registry instead of the old hardcoded placeholder flow
- Analyze persists stage-owned artifacts for ingest, normalize, segmentation, mesh, PTv3/landmarks, registration, measurements, and findings under the active transient session `analytics/derived/` tree
- Analyze now resolves the active installed production segmentation bundle and runs it through the dedicated Windows-safe nnU-Net sidecar runtime
- the mesh stage now converts segmentation label maps into raw, measurement-grade, and inference-grade per-vertebra triangle meshes plus PTv3-ready point clouds
- segmentation now persists additive per-label ROI statistics, and mesh plus registration now emit prepared baseline and standing scene manifests for faster Measurement and Report loading
- Import now surfaces compact analysis status and review-focus summaries from the real manifest outputs
- pipeline runs now record requested versus effective device metadata plus stage-local performance traces under each derived stage root
- the next product milestone is refreshing the production VERSe-backed `nnU-Net v2 ResEnc-L` bundle as new folds land and then hardening the downstream geometry stages

## Setup

```powershell
cd D:\claude\spinelab
conda env remove -n spinelab-claude -y
mamba env create -f environment.yml
conda activate spinelab-claude
python -m pip install -e .
```

Recreate the app environment when you pick up the renderer-backend changes above. The desktop runtime now keeps `vtk`, `pyvista`, `pyvistaqt`, and `trimesh` in the pip-installed project dependencies so the interactive 3D stack comes from PyPI wheels instead of Conda's Mesa-backed build.

The app environment is also mirrored under `envs/app.yml` for the Conda-managed desktop baseline. After `python -m pip install -e .`, the Measurement and Report workspaces use `trimesh` to load standing `.glb` demo and registration scene assets, while `vtk` / `pyvista` / `pyvistaqt` stay on the wheel-based runtime path.

For interactive desktop 3D, the runtime must not resolve through Conda `mesalib`, `libgallium_wgl.dll`, or an env-local `OPENGL32.dll`. SpineLab probes the active renderer at startup, shows the loading capsule and GPU/CPU status in the header, and blocks interactive 3D tabs if it detects software OpenGL.

Repo hygiene:

- keep non-repo data, case inputs, exports, and derived outputs under `E:\data\spinelab`
- keep only two top-level data folders:
  - `E:\data\spinelab\raw_test_data`
  - `E:\data\spinelab\cases`
- use `E:\data\spinelab\raw_test_data` for raw or converted reference inputs
- use `E:\data\spinelab\cases` as the default directory for saved `.spine` packages
- transient unsaved sessions live under `%LOCALAPPDATA%\SpineLab\sessions`, not under the data root
- legacy folder-backed cases may still exist as migration inputs, but `.spine` is now the only normal durable saved-case format
- do not use repo-root scratch folders as the long-term home for outputs
- treat `prototypes/electron-ui/` as a frozen reference, not the active runtime

## Sidecar Environments

- `envs/nanodrr.yml`: DRR sidecar baseline
- `envs/polypose.yml`: registration sidecar baseline
- `envs/landmarkpt.yml`: landmark research sidecar baseline
- `envs/cads_nnunet_win.yml`: local Windows CADS composite nnU-Net sidecar

These sidecars target Python `3.10` to `3.12` and keep heavyweight ML dependencies out of the main app environment. Individual backends may pin their own PyTorch and CUDA stacks as needed.

## Launch

```powershell
spinelab
```

Or:

```powershell
python -m spinelab.main
```

The Import workspace now keeps the image import control at the top of the `Images` section, while the left action card concentrates the `Pose Engine` selector, comparison selectors, the Turbo performance control, and `Analyze`. `Pose Engine` is now the explicit workflow gate for single-pose versus dual-pose analysis: choosing `Single Pose` expands a single full-width `Primary` modality selector, while choosing `Dual Pose` expands the split `Primary` and `Secondary` selectors. The Analyze button arms only when the currently selected pose engine has all required modality slots configured. The Import center toolbar now owns the CT z-stack slice slider, and the AP, LAT, and CT viewports render inside matching rounded cards instead of sharing a bare splitter surface. Analyze is the primary product execution path: it now runs the real in-app stage chain and writes stage-owned artifacts for segmentation, mesh, PTv3/landmarks, registration, measurements, and findings. Import also surfaces compact analysis-status and review-focus cards so model/version/provenance information stays in the app instead of living only in files on disk. Measurement and Report remain pending until `Analyze` completes from Import for the current case session, so switching tabs alone does not preload models, metrics, or report content. If you open Measurement before Analyze, each viewport stays black and shows a red `No Analysis Performed` warning. When Analyze completes, SpineLab automatically switches to Measurement and removes the pending warnings. Once unlocked, the Measurement toolbar keeps annotation tools on the left and render mode plus discrete `Low`, `Med`, and `High` detail controls on the right so mesh-detail changes apply on a single click instead of continuously during a slider drag. The Measurement left action card now owns `Supine` and `Standing` visibility toggles, `Set Reference Frame`, `Save Measurements`, and `Export Model`. Selecting vertebrae or pelvis only changes the active selection set; the reference basis now changes only when `Set Reference Frame` is pressed, so the global axis, standing registration offset, and orbit-up axis stay stable until the user explicitly re-anchors them.
If the user tries to close or replace the current case while `Analyze` is still running, SpineLab now treats that as a cancellation path rather than a save path. The confirmation dialog offers `Cancel Processing and Discard` or `Keep Working`; it does not offer `Save` while backend inference is still active.
The first imported CT now auto-claims the CT viewport when it is empty, and the first imported X-rays now auto-claim AP or LAT when their filename or DICOM metadata makes the projection unambiguous. If projection inference is ambiguous, the asset stays in the library for manual drag-and-drop assignment.
The live product path now defaults to the active installed production segmentation bundle. The Import workspace surfaces that resolved bundle as a read-only status label, and there is no in-app segmentation model picker for operators. The current temporary production default is `SkellyTour`, while the VERSe20 ResEnc nnU-Net bundles are quarantined behind explicit debug activation. If no safe production bundle is installed, Analyze fails closed with an explicit setup error instead of silently falling back. Legacy or debug segmentation profiles are promoted back to the production path when opened through the operator workflow. `Scaffold` remains internal to debug and test flows only.
`Tools -> Segmentation Backends...` is now the dev and research surface for workstation-level backend evaluation. It exposes the canonical four-backend matrix: VERSe20 `fold 0`, VERSe20 `fold 1`, `TotalSegmentator`, and `SkellyTour`. The dialog can install or register those backends, health-check their runtime environments, and activate one backend for subsequent `Analyze` runs without adding any per-case model selector to the operator workflow. The VERSe20 nnU-Net bundles are treated as debug-only until the ROI and preflight recovery work lands; setting `SPINELAB_ENABLE_DEBUG_SEGMENTATION_BUNDLES=1` before launch re-enables explicit nnU-Net debug activation.
The File menu now exposes `New Case`, `Open Case...`, `Open Legacy Case Folder...`, `Save Case`, `Save Case As...`, `Export Package Folder...`, and `Export Assets...` for the new `.spine` case workflow.
The Import Patient Explorer now shows saved `.spine` packages from the recent/opened package catalog only. Right-click `Remove from Explorer` and `File -> Clear Cases` remove entries from that catalog without deleting anything from disk.
`Make DRRs for Testing` now writes temporary bilateral AP/LAT CT projections into the current transient session `drr` folder and assigns them as the active standing inputs. Those testing DRRs are explicit surrogates and not calibrated NanoDRR outputs.
`Export Model` now prompts for a destination folder and writes a structured export bundle there. The bundle includes selected baseline meshes, copied standing scene assets, copied standing AP/LAT inputs when present, a measurements PDF/JSON pair, copied stage artifacts, backend provenance for the segmentation source, and current scaffold bilateral standing mesh projections. Those standing projections are explicitly marked as mesh-projection scaffolds until the true NanoDRR stage lands. Export folder naming now includes the active backend id when provenance is available so fold-comparison renders do not become ambiguous.
The header loading capsule now activates during case loads, Analyze-triggered workspace preparation, workspace rebuilds, and heavy tab switches so long UI transitions surface as explicit loading states instead of silent stalls.

After `Analyze`, SpineLab now builds Import, Measurement, and Report immediately instead of waiting for the first Measurement/Report tab switch. Measurement also opens baseline-only by default and no longer forces pelvis as the initial primary selection.
Measurement and Report now read structured metric records from the manifest first, so demo and target values surface with stage and provenance instead of generic placeholder copy.
The first non-demo measurement slice is now a single-pose native-3D package derived directly from landmark primitives. The currently supported native metrics are disc height, listhesis, segmental lordosis or kyphosis, lumbar lordosis, and thoracic kyphosis. Unsupported global or radiograph-equivalent metrics remain explicit fail-closed records instead of placeholder numbers.

## Case Format

SpineLab now uses a single `.spine` file as the normal durable case format.

- `File -> Open Case...` opens an existing `.spine` package.
- `File -> Open Legacy Case Folder...` loads a folder-backed legacy case into a transient session so it can be resaved as `.spine`.
- `File -> Save Case` updates the current package in place.
- `File -> Save Case As...` writes a new package with a new `case_id`.
- `File -> Export Package Folder...` writes an unpacked copy of the package layout.
- `File -> Export Assets...` writes selected asset groups to a chosen destination.

The app works inside a transient workspace under `%LOCALAPPDATA%\SpineLab\sessions` while the session is open. `Analyze` writes stage-owned artifacts into that transient workspace, and those artifacts become durable only when the user saves the case as `.spine`.

SpineLab intentionally does not provide crash recovery in `v0.1`. If the app terminates unexpectedly, unsaved PHI is not restored; orphaned transient sessions are purged on next startup.

## Production Segmentation

SpineLab uses CADS pretrained nnU-Net models as the production segmentation backend. Installed bundles live under:

```text
E:\data\spinelab\raw_test_data\models\segmentation\<bundle-id>\
```

Two CADS composite bundles are available:
- **CADS Skeleton** (`cads-skeleton`): vertebrae, ribs, appendicular bones, sternum, spinal canal (61 classes, 4 models)
- **CADS Skeleton Plus** (`cads-skeleton-plus`): skeleton + vasculature + spinal cord (68 classes, 7 models)

The active bundle id is stored in user settings, while each Analyze run records the resolved bundle id, checkpoint id, driver id, environment id, and a per-run segmentation provenance manifest under the case `analytics\derived\segmentation` stage root. The CADS composite driver runs each sub-model task sequentially via the nnU-Net sidecar, then merges predictions using label cherry-pick maps.

## GUI Validation

For UI work, the full SpineLab shell is the source of truth.

- use standalone widgets or direct workspace windows only for narrow mechanical debugging
- do final visual evaluation, layout checks, and signoff through the real app bootstrap in `python -m spinelab.main` or equivalent tests that instantiate `MainWindow`
- treat direct `workspace.show()` harnesses as insufficient for judging shell chrome, spacing, launch geometry, sidebar behavior, and cross-workspace state
- prefer validation on the real `Analyze -> Review` path whenever the edit affects operator-visible workflow

## Checks

Use [docs/agent_check_runbook.md](/D:/claude/spinelab/docs/agent_check_runbook.md) as the source of truth for recurring validation tiers, status vocabulary, known-baseline handling, and agent reporting. The commands below are only the fast local gate entrypoint.

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\run_repo_checks.ps1
```

The bare `python` in a shell may resolve to a non-project interpreter. The check script always targets the `spinelab-claude` environment so repo verification matches the real app runtime.
Qt tests now bootstrap the production SpineLab `QApplication` setup, and shell-level launch or layout checks should target `MainWindow` rather than showing embedded workspaces as fake top-level windows.

## Mesh Benchmarking

For scheduled optimization audits, delta reporting, and workstation-only prerequisites, follow [docs/agent_check_runbook.md](/D:/claude/spinelab/docs/agent_check_runbook.md).

Use the data-root-backed benchmark harness to compare mesh extractors on real segmentation outputs:

```powershell
python .\tools\benchmark_mesh_pipeline.py
```

Or point it at specific segmentation contracts or case folders:

```powershell
python .\tools\benchmark_mesh_pipeline.py E:\data\spinelab\cases\my-case\analytics\derived\segmentation\segmentation.json
```

The benchmark writes per-vertebra results plus an aggregate summary under `E:\data\spinelab\raw_test_data\_benchmarks\mesh_pipeline\`.

For cold import and startup-sensitive paths:

```powershell
python .\tools\benchmark_startup.py
```

## Structure

- `prototypes/electron-ui/`: frozen UI baseline copied from `D:\dev\GUI_test\figma_UI_code`
- `src/spinelab/`: native app code
- `src/spinelab/pipeline/`: backend contracts, orchestration, device detection, and stage scaffolding
- `envs/`: pinned app and backend sidecar environment manifests
- `docs/project_brief.md`: short operational project brief for agents and engineers
- `docs/data_contracts.md`: artifact schemas, coordinate spaces, and transform bookkeeping
- `docs/measurement_spec.md`: versioned measurement rules and validity gating
- `docs/ontology/spinelab_vertebral_labeling_ontology.yaml`: canonical imported vertebral labeling ontology and measurement dependency spec; frozen and not editable without explicit user approval
- `docs/spinelab_manifesto.md`: long-form project manifesto and roadmap
- `docs/roadmap.md`: GUI-first implementation sequence for the scientific pipeline stages
- `docs/design_system.md`: locked palette, typography, geometry, and layout rules
- `docs/code_review.md`: proactive and recursive review checklist
- `docs/agent_check_runbook.md`: canonical recurring CI, workstation smoke, and optimization check runbook for agents
- `tools/check_theme_usage.py`: enforces theme-token usage outside the theme modules
- `tools/run_repo_checks.ps1`: runs the standard repo checks in the correct app environment
- `tools/benchmark_mesh_pipeline.py`: benchmarks the mesh extractor candidates on data-root-backed segmentation outputs
