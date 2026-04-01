# SpineLab 0.2 Instructions

## Scope

- Work only inside `D:\claude\spinelab`.
- Never touch legacy code folders outside the repo.
- Non-repo case data lives under `E:\data\spinelab`.
- Keep the data root constrained to two top-level folders only:
  - `E:\data\spinelab\raw_test_data`
  - `E:\data\spinelab\cases`
- Use `E:\data\spinelab\raw_test_data` for raw or converted reference inputs.
- Use `E:\data\spinelab\cases` as the default location for saved `.spine` case packages.
- Treat transient runtime sessions as local-app-data state under `%LOCALAPPDATA%\SpineLab\sessions`, not as durable case storage.
- Legacy folder-backed cases may still appear as migration inputs. If such folders are touched explicitly, they must keep only these root subfolders:
  - `ct`
  - `mri`
  - `xray`
  - `drr`
  - `3d`
  - `analytics`
- Keep legacy-case meshes under `3d\supine` or `3d\standing`.
- Keep manifests, stage artifacts, exports, reports, and other program-managed legacy case data under `analytics`.
- Media assets (graphics, renders, design files, papers) live under `E:\data\spinelab\media`.
- Treat `prototypes/electron-ui/` as a frozen reference, not the active runtime.

---

## Canonical Docs

- Read `docs/project_brief.md` first for onboarding, non-negotiables, and current implementation priorities.
- Use `docs/data_contracts.md` when touching schema, artifacts, coordinate systems, transforms, or pipeline interfaces.
- Use `docs/measurement_spec.md` when touching metric definitions, required primitives, validity gating, or uncertainty fields.
- Use `docs/agent_check_runbook.md` when defining, running, or reporting recurring validation, CI, workstation smoke, or optimization audits.
- Use `docs/ontology/spinelab_vertebral_labeling_ontology.yaml` when touching the imported spine anatomy ontology, landmark naming, or measurement dependency definitions.
- Use `docs/spinelab_manifesto.md` for the full long-form project rationale, roadmap, research context, and references.
- Do not load `docs/spinelab_manifesto.md` by default for small implementation tasks when the brief or the specific contract/spec doc is sufficient.

---

## SpineLab Project Context (Read First)

SpineLab is a **3D spine analysis system** that quantifies vertebral motion and alignment.

### Core Objective
Transform **supine CT/MRI-derived 3D geometry** into a **standing pose defined by 2D X-rays (EOS or C-arm)** and compute clinically relevant measurements.

### Core Pipeline

CT/MRI Volume
→ nnU-Net v2 ResEnc-L Segmentation (vertebrae labeled individually)
→ Per-Vertebra Mesh Generation
→ PTv3 Dense Vertebra Vertex Groups / Substructures
→ Landmark + Primitive Derivation From PTv3 Vertex Groups
→ PolyPose-Style Registration (supine → standing or other target pose)
→ Measurement Engine (3D + radiographic-equivalent)
→ Visualization (UI)

### Long-Term Goal
- Intraoperative 3D alignment + measurement system
- Sub-millimeter accuracy target (~1 mm)

---

## Default Technical Decisions (Do Not Deviate Without Reason)

### Segmentation
- Default: **Residual Encoder nnU-Net**
- High-accuracy alternative: **MedNeXt**
- Bootstrap only: **TotalSegmentator**
- The in-app production path now resolves the active installed nnU-Net bundle through the local Windows sidecar runtime.
- Do not expose a user-facing segmentation-model selector. Production bundle changes are an installation and activation step, not an operator workflow choice.
- Keep **Scaffold** available only for debug or test workflows. Do not use it as a silent production fallback.

### Registration
- Use **polyrigid vertebra-level transforms**
- PolyPose-style methods are the current target

### Point Cloud / Mesh Learning
- DO NOT use classification models
- Use:
  - **Dense point segmentation**
  - **Anatomical correspondence**
  - **Canonical vertebral frame normalization**
- Keep **triangles** as the canonical stored/exported mesh type unless a downstream tool requires something else
- Keep a **measurement mesh**, a lighter **inference mesh**, and a PTv3-ready **point-cloud export** distinct
- PTv3 is for **dense vertebra vertex groups / substructures**
- Landmarks and primitives are derived from those PTv3 vertex groups, not from a disconnected classifier

---

## Required Data Contracts

### Each Vertebra MUST Have:
- Superior endplate plane
- Inferior endplate plane
- 4 body corners
- Posterior wall
- Endplate midpoints
- Vertebral centroid

### Global Structures:
- S1 endplate + midpoint
- Posterior-superior S1 corner
- Femoral head centers (both)
- C7 centroid

---

## Critical System Constraints

- All measurements must exist in a **single global coordinate system**
- Never mix coordinate frames silently
- Measurement definitions must be **locked and consistent**
- UI convenience must NEVER override clinical correctness
- The default registration target is a **generic calibrated multi-view pose bundle**
- EOS / biplanar X-ray is the first concrete adapter for target-pose recovery

### Field-of-View Constraints

If imaging is incomplete:
- You MAY compute:
  - Disc height
  - Listhesis
  - Segmental lordosis

- You MAY NOT compute:
  - SVA
  - Pelvic parameters (PI/PT/SS)
  - Full scoliosis metrics

---

## Current Implementation Priorities

1. Vertebra segmentation (CT/MRI)
2. Mesh generation pipeline
3. Landmark + substructure detection
4. Registration-ready landmark/primitives from PTv3 vertex groups
5. Measurement engine
6. Registration (after above are stable)

---

## Repo Layout

- `src/spinelab/`: active product code
- `src/spinelab/ui/theme/`: the only place raw color, font, spacing, and radius literals belong
- `docs/project_brief.md`: operational quick-start and current-phase brief
- `docs/data_contracts.md`: artifact, schema, and transform contract source
- `docs/measurement_spec.md`: measurement definitions and validity rules
- `docs/spinelab_manifesto.md`: long-form project manifesto
- `docs/design_system.md`: visual source of truth
- `docs/code_review.md`: review rubric
- `docs/agent_check_runbook.md`: recurring validation, CI, workstation smoke, and optimization check source of truth

---

## Workflow

- Search for prior art and all affected call sites before adding new helpers or patterns.
- Inspect sibling workspaces and shared services when touching shared UI or types.
- Keep changes vertical and runnable.
- Build the mechanics that will actually be used in the GUI.
- For UI edits, treat standalone widget or workspace windows as debug-only scaffolding. Final visual evaluation and signoff must happen in the full `MainWindow` shell through the real app bootstrap.
- Treat `Analyze -> Review` in the app as the primary product path for every milestone.
- Do not prioritize CLI-only workflows, offline QC galleries, or debug-only artifact dumps over in-app mechanics.
- Roadmap planning should be **GUI-first** and **vertical-slice-first** so each stage remains independently swappable without breaking the chain.
- Keep `AGENTS.md`, `README.md`, and the affected files under `docs/` in sync whenever user-facing workflows, dependencies, or architectural contracts change.
- Preserve the `.spine` saved-case model: no silent durable writes during routine import or analysis, and no crash-recovery retention of unsaved PHI unless the user explicitly asks for a new policy.
- Land large backend work in small commits when a vertical slice is runnable and verified.
- Treat `docs/ontology/spinelab_vertebral_labeling_ontology.yaml` as frozen. Do not edit it without explicit user approval.

## Writing Style

- Use academic prose when writing English human text in documentation, UI copy, reports, and other reader-facing narrative content unless the user explicitly asks for a different register.
- Prefer precise terminology, restrained tone, and clinically or scientifically accurate phrasing over conversational language.

---

## Viewport Interaction Rules

- All 3D, orthographic, and 2D viewports:
  - Middle mouse = pan
  - Scroll = zoom
- CT stack viewport:
  - Scroll = slice
  - Ctrl + scroll = zoom

- Keep `+Z` as anatomical up for all 3D work.

---

## Runtime Architecture Rules

- Main app:
  - Python 3.12
- Research / ML:
  - Lives in `envs/`
  - Must support CPU fallback

---

## Theme Rules

- Keep every visible block radius concentric with its parent by stepping down through the shared geometry tokens instead of reusing the same radius at multiple nested depths.
- Treat the UI hierarchy as:
  - shell/window
  - panel
  - first inset child
  - nested inset child
- Use the next smaller shared radius token at each deeper level.
- Continuously audit concentricity after any UI layout, card, toolbar, viewport wrapper, or inspector change.
- Text brightness must follow block depth:
  - higher-level containers may use brighter text
  - deeper nested blocks must not become brighter than their parent
  - values and labels inside nested inspector/action/summary cards should step down to the deeper text roles unless a semantic state color is intentionally applied
- Keep all raw spacing and radius literals inside `src/spinelab/ui/theme/`.

---

## Completion Loop

- For UI work, validate the final behavior in the real app shell rather than relying on direct `workspace.show()` harnesses.
- Use `docs/agent_check_runbook.md` as the source of truth for recurring validation tiers, status vocabulary, known baselines, and agent-facing reporting.
- Run `python tools/check_theme_usage.py`.
- Run:
  - `python -m ruff check .`
  - `python -m mypy src`
  - `python -m pytest`
- Review diff against `docs/code_review.md`
- Ensure viewports still function correctly
