# Roadmap

## Current Foundation

The repo now has the GUI-first scientific pipeline foundation in place:

1. `Analyze` runs a dependency-aware in-app stage chain instead of the old hardcoded four-stage placeholder flow.
2. Stage-owned artifacts are persisted under the active transient session `analytics/derived/` tree for:
   - ingest
   - normalize
   - segmentation
   - mesh
   - landmarks / PTv3 vertex groups
   - registration
   - measurements
   - findings
3. `CaseManifest` remains the GUI/session index while the durable saved case is a `.spine` package.
4. Import surfaces compact analysis status and review-focus summaries from the real manifest outputs.
5. Measurement can already discover generated mesh assets and standing-pose scene assets through the existing GUI path.

## Milestone Rule

Every milestone must be:

- operator-visible in the GUI
- exercisable through the real `Analyze -> Review` flow
- contract-stable enough that later stages can be swapped independently
- judged by “usable in app”, not “script ran once”

Do not prioritize CLI-only execution paths, offline QC galleries, or debug-only artifact dumps over the real product workflow.

## Canonical Scientific Chain

`nnU-Net v2 ResEnc-L vertebra segmentation -> per-vertebra mesh generation -> PTv3 dense vertebra vertex groups/substructures -> landmark/primitives derived from PTv3 vertex groups -> PolyPose-style registration to target pose from calibrated multi-view imaging -> 3D motion/alignment quantification in one global coordinate system`

## Phase A — Architecture Cleanup

Goal: finish locking the scientific core around clean stage contracts.

Deliverables:

- keep `CaseManifest` as the GUI/session index only
- keep downstream stages reading artifact files, not convenience fields
- preserve explicit coordinate frames and transform bookkeeping
- keep generated GUI summaries as views over artifact truth, not replacement truth

Exit criteria:

- rerunning one stage invalidates stale downstream stage state cleanly
- stage contracts stay versioned and independently swappable
- Import, Measurement, and Report read manifest-backed summaries derived from artifacts

## Phase B — CT Segmentation Vertical Slice

Goal: land the first production scientific module.

Deliverables:

- train custom `nnU-Net v2 ResEnc-L` on VERSe CT
- freeze dataset conversion, ontology, patient split policy, and exported bundle format
- replace scaffold segmentation outputs with real sidecar inference
- keep segmentation review in Import as the first operator-visible output

Exit criteria:

- Analyze runs real segmentation through the app
- model name, version, checkpoint, uncertainty, and failure state surface in Import
- segmentation artifacts are persisted with contract-complete provenance

## Phase C — Per-Vertebra Mesh Slice

Goal: convert labeled vertebrae into reusable geometry products.

Deliverables:

- one measurement-grade mesh per vertebra
- one lighter inference mesh per vertebra
- point-cloud export path for PTv3
- data-root-backed benchmark comparing `vtkDiscreteFlyingEdges3D` and `vtkSurfaceNets3D`
- in-app 3D review of generated geometry through the existing Measurement workspace

Exit criteria:

- Measurement loads the real generated meshes, not fallback/demo geometry
- mesh artifacts preserve segmentation provenance and coordinate-frame metadata
- benchmark outputs are written under `E:\data\spinelab\raw_test_data\_benchmarks\mesh_pipeline\` and summarize runtime, Dice, and QC pass rate

## Phase D — PTv3 Substructure + Landmark Slice

Goal: learn vertebra-local anatomy in a way that supports downstream mechanics.

Deliverables:

- PTv3 dense vertex-group / substructure prediction on vertebra point clouds
- landmark and primitive derivation from those PTv3 vertex groups
- vertebra-local frame output with uncertainty and support metadata
- anomaly / pathology heads remain optional and deferred

Exit criteria:

- required vertebral primitives are contract-complete
- primitive provenance points back to PTv3 outputs and supporting geometry
- the app surfaces landmark readiness through existing review surfaces

## Phase E — Registration Slice

Goal: recover target pose in one shared global frame.

Deliverables:

- generic calibrated multi-view target-pose contract
- EOS / biplanar X-ray as the first concrete adapter
- PolyPose-style vertebra-level polyrigid transforms
- pose graph persistence and standing-pose scene review in Measurement

Exit criteria:

- registration writes per-vertebra transforms into one explicit patient/global frame
- standing review assets load in the real GUI
- calibration and uncertainty failures surface as reviewable state, not hidden logs

## Phase F — Motion And Alignment Quantification

Goal: compute clinically meaningful values from the registered 3D geometry.

Deliverables:

- native 3D measurements first
- projected / radiographic-equivalent metrics kept explicitly separate
- validity gating and uncertainty on every metric
- findings logic derived from locked measurement definitions

Exit criteria:

- unsupported field-of-view metrics fail closed
- Report reads artifact-backed measurements and findings
- no core clinical metric depends on legacy demo-only manifest fields
