# SpineLab Project Brief

This is the short operational brief for day-to-day engineering work.

Use this document first. Open [docs/spinelab_manifesto.md](/D:/claude/spinelab/docs/spinelab_manifesto.md) only when the task needs broader rationale, roadmap context, or reference support.

## Thesis

SpineLab models the spine as a patient-specific articulated anatomical system. The goal is to recover clinically meaningful vertebral pose and motion from sparse 2D imaging by combining:

- patient-specific CT or MRI anatomy
- articulated vertebra-level pose recovery
- anatomically grounded landmarks and substructures
- versioned measurement logic
- uncertainty-aware visualization and review

## North Star

Take preoperative or baseline CT/MRI-derived 3D anatomy, infer its pose in a new posture from sparse 2D X-rays, and compute clinically meaningful spinal and spinopelvic measurements with uncertainty and QC.

## First Product

The first product is not an end-to-end black box. It is a modular, auditable pipeline:

- ingest DICOM, metadata, and calibration
- segment and label vertebrae
- extract meshes and surfaces
- infer landmarks and substructures
- recover articulated sparse-view pose
- compute versioned measurements
- show results, provenance, QC, and manual edit points in the GUI

## Current Default Technical Decisions

- Segmentation default: CADS pretrained composite nnU-Net models (Skeleton: 61 classes / 4 tasks, Skeleton Plus: 68 classes / 7 tasks)
- Landmark and shape modeling: dense point segmentation plus correspondence, not generic classification
- Registration default: PolyPose-style vertebra-level polyrigid registration
- Measurement strategy: keep projected radiograph-equivalent metrics separate from native 3D metrics
- Trust model: every module emits uncertainty, provenance, and failure flags

## Non-Negotiables

1. Measurement definitions are versioned.
2. Every output has provenance back to source images, segmentations, landmarks, and transforms.
3. Every module exposes confidence or uncertainty.
4. Patient-level splits only.
5. Manual correction must remain possible.
6. Clinical correctness beats UI convenience.
7. Do not silently mix coordinate frames.
8. Do not compute metrics unsupported by field of view.

## GUI Validation Protocol

- Standalone widgets or direct workspace windows are acceptable only for narrow mechanical debugging.
- Final visual evaluation and signoff for UI edits must happen in the full `MainWindow` shell through the real app bootstrap.
- Shell-level launch, spacing, sidebar, and cross-workspace checks must target the real workspace activation path, not direct `workspace.show()` on embedded pages.
- Prefer validating user-facing workflow changes on the real `Analyze -> Review` path.

## Canonical Pipeline

```text
CT/MRI volume
  -> segmentation + vertebra instance labeling
  -> mesh and surface extraction
  -> vertebral landmarks + substructures
  -> vertebra local frames + articulated spine graph
  -> EOS / C-arm ingestion + calibration
  -> polyrigid 2D/3D registration
  -> posed 3D spine model
  -> measurement engine
  -> uncertainty, QC, and manual correction
  -> GUI visualization and export
```

## Current Phase

The repo is now in GUI-first scientific-core-foundation stage.

What exists now:

- native PySide6 shell and viewport system
- transient session workspace plus `.spine` package open/save/export services
- import, measurement, and report workspaces
- dependency-aware in-app pipeline registry for ingest, normalize, segmentation, mesh, landmarks, registration, measurements, and findings
- stage-owned artifacts persisted under the transient session `analytics/derived/` tree and packaged on save
- a production in-app segmentation path that resolves an installed nnU-Net bundle and executes it through the local Windows sidecar runtime
- an operator workflow that exposes only the resolved production segmentation backend status rather than any per-case model selector
- VTK-based per-vertebra mesh extraction from segmentation label maps with raw, measurement-grade, and inference-grade outputs
- additive segmentation label statistics and prepared-scene artifacts that let downstream stages reuse ROI bounds and scene metadata instead of rescanning cases
- PTv3-ready point-cloud export from the measurement mesh plus a data-root-backed benchmark harness for mesh extractor comparison
- a frozen shared anatomy ontology contract for canonical levels, surface patches, primitives, and global structures
- compact Import-side analysis status and review-focus summaries driven by the real manifest outputs
- an explicit Import-side `Pose Engine` gate that arms either a single primary modality path or a dual primary-plus-secondary path before `Analyze`
- runtime device metadata and per-stage performance traces persisted alongside stage-owned artifacts
- sidecar environment manifests for segmentation, DRR, registration, and landmark research tools
- hardware OpenGL probing and software-render blocking for interactive 3D
- stabilized measurement viewport controls, pose toggles, and workspace isolation
- `.spine` as the sole normal saved-case format with no crash recovery for unsaved PHI
- a segmentation-backend manager that can activate installed CADS composite bundles without adding any per-case selector to the operator workflow
- backend provenance now carried from segmentation into mesh, export, and review-facing measurement or report surfaces so qualitative fold-comparison renders remain attributable
- the first real single-pose native-3D measurement slice derived from landmark primitives, with disc height, listhesis, segmental lordosis or kyphosis, lumbar lordosis, and thoracic kyphosis available even when paired standing data are absent

What is still placeholder or scaffolded:

- higher-fold nnU-Net bundle refresh and future model-family replacement beyond the first production ResEnc baseline
- production PTv3 dense substructure inference
- production PolyPose registration against calibrated multi-view input
- clinically locked measurement implementation beyond the current artifact-backed scaffold metrics

## Immediate Next Implementation Priorities

1. Keep the operator workflow on the bundle-driven fail-closed production path with CADS as the production default, and handle backend changes through installation and activation rather than per-case selection. Reserve `Scaffold` for debug-only flows.
2. Tune and benchmark the mesh stage against real CADS composite outputs from the installed production bundles.
4. Extend the single-pose native-3D measurement slice while keeping unsupported radiograph-equivalent or full-field-of-view metrics explicitly invalid.
5. Replace scaffold PTv3 vertex-group and landmark outputs with real dense vertebra-local inference.
6. Replace scaffold registration with PolyPose-style target-pose recovery from calibrated multi-view input.
7. Keep QC, uncertainty, and validity gating explicit in every stage interface from day one.
8. Continue removing demo or placeholder measurement/report assumptions in favor of artifact-backed outputs.

## Necessary Components For The Next Vertical Slice

- segmentation sidecar that writes labeled-vertebra outputs into the existing artifact model
- mesh extraction stage with explicit source volume, label-map affine, spacing, and transform provenance
- shared anatomy ontology that every stage consumes instead of stage-local vertebra lists or PTv3-local ids
- benchmark harness that compares candidate mesh extractors on data-root-backed segmentation outputs
- PTv3 vertex-group package with landmark and primitive derivation from those groups
- static measurement engine that reads only the locked contracts and emits validity gating
- stage-level QC and uncertainty fields from segmentation through measurement
- sidecar execution wrappers that can be invoked from the desktop orchestrator without changing the GUI contract

## Required Anatomy for the First Valid Measurement Package

Tier 1 per vertebra:

- superior endplate plane
- inferior endplate plane
- anterior-superior corner
- posterior-superior corner
- anterior-inferior corner
- posterior-inferior corner
- posterior wall
- superior endplate midpoint
- inferior endplate midpoint
- vertebral centroid

Tier 2 global structures:

- S1 superior endplate and midpoint
- posterior-superior S1 corner
- left and right femoral head centers
- C7 centroid

## Field-of-View Gating

If imaging is incomplete:

- You may compute disc height, listhesis, and segmental lordosis.
- You may not compute SVA, pelvic parameters, or full scoliosis metrics.

## Read Next

- Open [docs/data_contracts.md](/D:/claude/spinelab/docs/data_contracts.md) before changing artifacts, schemas, transforms, or coordinate handling.
- Open [docs/measurement_spec.md](/D:/claude/spinelab/docs/measurement_spec.md) before changing metrics, validity logic, or required primitives.
- Open [docs/ontology/spinelab_vertebral_labeling_ontology.yaml](/D:/claude/spinelab/docs/ontology/spinelab_vertebral_labeling_ontology.yaml) before changing ontology, landmark naming, or measurement dependency definitions. Do not edit it without explicit user approval.
- Open [docs/spinelab_manifesto.md](/D:/claude/spinelab/docs/spinelab_manifesto.md) when you need roadmap, risk, data-strategy, or literature context.
