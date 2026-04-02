# SpineLab Data Contracts

This is the operational source for artifact schemas, coordinate-space rules, and transform bookkeeping.

Keep this document in sync with [docs/spinelab_manifesto.md](/D:/claude/spinelab/docs/spinelab_manifesto.md).

## Contract Principles

1. Every artifact records provenance.
2. Every artifact records the coordinate frame it lives in.
3. Every stage preserves explicit transforms rather than silently collapsing frames.
4. Every downstream measurement must be reproducible from stored artifacts and transforms.
5. UI display transforms are not clinical geometry transforms.

## Canonical Coordinate Spaces

Maintain explicit transforms between these spaces:

1. Native image space
   - Original DICOM voxel geometry and orientation.
2. Normalized volume space
   - Resampled and orientation-normalized volume used for downstream processing.
3. Surface or mesh space
   - Geometry derived from segmentation.
4. Vertebra local anatomical frame
   - Per-vertebra frame for substructures, local motion, and canonicalization.
5. Patient body frame
   - Shared 3D frame for the posed anatomy and whole-patient measurements.
6. Imaging system frame
   - EOS or C-arm geometry and projection frame.
7. Display frame
   - GUI visualization frame only.

## Frozen Anatomy Ontology

SpineLab now treats anatomy ids as a shared product contract, not a PTv3 detail.

Rules:

- The canonical measurement-bearing spinal chain is fixed to:
  - `C7`
  - `T1-T12`
  - `L1-L5`
  - `S1`
- Extra or ambiguous levels do not change that chain.
- Variants are represented through observed-instance metadata, not by adding new canonical levels.
- The v1 core is additive-only:
  - no renames
  - no removals
  - no PTv3 class-index changes

### Frozen Surface Patch Classes

- `background_or_unknown = 0`
- `superior_endplate = 1`
- `inferior_endplate = 2`
- `posterior_body_wall = 3`
- `vertebral_body_surface = 4`
- `left_pedicle = 5`
- `right_pedicle = 6`
- `left_facet_surface = 7`
- `right_facet_surface = 8`

### Frozen Primitive Ids

- `vertebral_centroid`
- `superior_endplate_plane`
- `inferior_endplate_plane`
- `anterior_superior_corner`
- `posterior_superior_corner`
- `anterior_inferior_corner`
- `posterior_inferior_corner`
- `posterior_wall_line`
- `superior_endplate_midpoint`
- `inferior_endplate_midpoint`
- `vertebra_local_frame`

### Frozen Global Structure Ids

- `C7_centroid`
- `S1_superior_endplate_plane`
- `S1_superior_midpoint`
- `posterior_superior_S1_corner`
- `left_femoral_head_center`
- `right_femoral_head_center`
- `bicoxofemoral_axis_midpoint`
- `sacral_center`

### Observed Structure Context

Observed structures should carry:

- `structure_instance_id`
- `display_label`
- `standard_level_id | None`
- `structure_type`
- `order_index | None`
- `numbering_confidence`
- `variant_tags`
- `supports_standard_measurements`
- `superior_neighbor_instance_id | None`
- `inferior_neighbor_instance_id | None`

Examples:

- A standard L3 vertebra keeps `standard_level_id = "L3"`.
- A `T13`-like case keeps the observed structure but uses:
  - `standard_level_id = null`
  - `variant_tags = ["extra_thoracic_segment", "numbering_ambiguous"]`
  - `supports_standard_measurements = false`

## Imported Measurement Ontology Package

The repo now stores a separate imported ontology specification as a single canonical file:

- [docs/ontology/spinelab_vertebral_labeling_ontology.yaml](/D:/claude/spinelab/docs/ontology/spinelab_vertebral_labeling_ontology.yaml)

That file is frozen and must not be edited without explicit user approval.

It is intentionally broader than the current executable runtime ontology. It defines:

- landmark codes
- landmark geometry types
- measurement dependency requirements
- implementation-module ordering
- naming examples
- field-of-view support examples

It does not automatically override the runtime ids in `src/spinelab/ontology/`.

Until explicit approval is given, treat the relationship as:

- `src/spinelab/ontology/` is the executable source of truth for current code
- `docs/ontology/spinelab_vertebral_labeling_ontology.yaml` is the imported measurement-oriented specification package

Do not silently rename runtime ids to match imported wording. Any reconciliation between the two layers must be reviewed deliberately and versioned explicitly.

## Vertebral Local Frame

Recommended initial definition:

- Origin: vertebral centroid or midpoint between superior and inferior endplate midpoints
- Superior-inferior axis: mean endplate normal or endplate-center axis
- Left-right axis: pedicle-center axis
- Anterior-posterior axis: cross product completing a right-handed frame

This frame must be explicit and versioned if refined later.

## Transform Bookkeeping

Every reproducible output should be traceable to:

- source volume ID
- segmentation version
- mesh version
- landmark model version
- registration version
- measurement definition version
- relevant transforms between all referenced spaces

## Saved Case And Session Storage Contract

SpineLab now distinguishes between:

1. the saved durable case package, and
2. the transient runtime session workspace.

The normal durable case format is a single `.spine` file. The detailed saved-case format is defined in [docs/spine-format.md](/D:/claude/spinelab/docs/spine-format.md).

### Saved Durable Case

The default user-facing save location remains `E:\data\spinelab\cases`, but the saved case itself is a single `.spine` ZIP package rather than a live managed folder tree.

The package layout is:

- `manifest.json`
- `dicom/ct/`
- `dicom/mri/`
- `dicom/xray/`
- `ct/`
- `mri/`
- `xray/`
- `drr/`
- `3d/supine/`
- `3d/standing/`
- `analytics/`

Rules:

- Original DICOM bytes are preserved under `dicom/...`.
- Standardized working CT lives under `ct/`.
- MRI and X-ray working assets live under `mri/` and `xray/`.
- Generated or imported DRRs live under `drr/`.
- Temporary `File -> Make DRRs for Testing` outputs, when saved, also live under `drr/` and remain explicit CT-projection surrogates until calibrated NanoDRR generation lands.
- Supine and standing geometry live under `3d/supine/` and `3d/standing/`.
- Stage-owned machine-readable outputs, reports, and related derived assets live under `analytics/`.

### Transient Runtime Session

While the app is open, SpineLab works in a transient session workspace under:

- `%LOCALAPPDATA%\SpineLab\sessions\<session-id>\workspace\`

The workspace mirrors the saved package layout exactly:

- `dicom/ct/`
- `dicom/mri/`
- `dicom/xray/`
- `ct/`
- `mri/`
- `xray/`
- `drr/`
- `3d/supine/`
- `3d/standing/`
- `analytics/`

Rules:

- Analyze writes stage-owned outputs into the transient session workspace.
- Runtime-only metadata such as the editable `CaseManifest` mirror and DICOM catalog live outside the saved payload under `%LOCALAPPDATA%\SpineLab\sessions\<session-id>\runtime\`.
- Unsaved transient sessions are not crash-recovered in `v0.1`; orphaned session roots are purged on next startup.

## Required Primitive Contracts

Per vertebra, the first valid measurement package requires:

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

Global structures required for full alignment:

- S1 superior endplate
- S1 superior midpoint
- posterior-superior S1 corner
- sacral midline or center
- left femoral head center
- right femoral head center
- bicoxofemoral axis midpoint
- C7 centroid

## Minimal Artifact Schemas

### `segmentation.json`

Should include:

- patient, study, and series IDs
- modality
- model name and version
- model display name
- segmentation profile
- label-map path
- source volume ID
- source normalized-volume artifact ID when available
- voxel spacing
- orientation
- coordinate frame
- model bundle id
- model family
- runtime driver id
- runtime environment id
- resolved checkpoint id
- segmentation run-manifest path
- QC summary
- per-label confidence when available
- observed structure-instance metadata for each vertebra entry that is actually present in the prediction volume
- additive per-label geometry statistics for downstream mesh reuse:
  - `voxel_count`
  - `ijk_bounds`
  - optional `center_hint_ijk`
  - retained `center_hint_patient_frame_mm`

Current segmentation profiles:

- `production`
- `scaffold`

Rules:

- `production` is the default in-app profile and must resolve one active installed segmentation bundle on the local machine.
- `production` must fail closed with an actionable error if no active bundle or required sidecar runtime is available.
- `scaffold` is retained only for debug or test flows and must never be selected silently as a production fallback.
- Legacy case manifests that still reference retired bootstrap profiles must be canonicalized back to `production` for the operator workflow.
- The real Import workflow must expose resolved production-backend status only; it must not expose a user-facing segmentation-model selector.
- `qc_summary.vertebra_count` must reflect only vertebra entries actually observed in the current prediction volume, not the full bundle label map.

### `bundle.json`

Installed production segmentation bundles live under:

- `E:\data\spinelab\raw_test_data\models\segmentation\<bundle-id>\`

Each bundle manifest must include at least:

- `bundle_id`
- `family`
- `display_name`
- `environment_id`
- `driver_id`
- `modality`
- `inference_spec`
- `checkpoints`
- `active_checkpoint_id`
- `label_mapping`
- `provenance`
- `runtime_root`

Rules:

- If the imported trainer tree contains multiple folds, installation must require an explicit `active_checkpoint_id`.
- Bundle activation is a machine-level operational choice and must not be inferred from the lowest fold index.

### `segmentation/run-manifest.json`

The production segmentation run manifest must record execution-time provenance, including:

- case id
- source volume id
- model bundle id and family
- driver id and runtime environment id
- resolved checkpoint id and checkpoint path
- runtime results root
- staged input and prediction paths
- sidecar log path when the backend writes verbose runtime output to a file
- executed command
- resolved device
- start and finish timestamps
- captured stdout and stderr

### `mesh_manifest.json`

Should include:

- source segmentation version
- source segmentation artifact ID
- source volume ID
- extraction algorithm
- label-map path and affine
- smoothing settings
- decimation settings
- point-cloud sampling settings
- raw mesh path
- high-resolution mesh path
- inference mesh path
- point-cloud path
- structure-instance metadata for each vertebra entry
- source coordinate frame
- coordinate frame
- crop bounds or ROI provenance for each vertebra
- QC summary and component statistics
- checksum

The current mesh stage writes triangle `.ply` files for:

- `3d/supine/raw/`
- `3d/supine/measurement/` measurement-grade meshes
- `3d/supine/inference/` lighter PTv3-facing meshes

It also writes PTv3-ready point clouds as compressed `.npz` files under `analytics/derived/mesh/point-clouds/`.

### `prepared_scene_baseline.json` and `prepared_scene_standing.json`

Should include:

- `schema_version`
- `pose_name`
- `coordinate_frame`
- source artifact ID for the mesh or registration stage
- prepared model entries with:
  - `vertebra_id`
  - `display_label`
  - `selection_key`
  - `mesh_path`
  - `pose_name`
  - `center_mm`
  - `extents_mm`
  - checksum or equivalent artifact identity
- optional rigid `transform_matrix` for prepared standing entries that reuse baseline meshes

Rules:

- Measurement and Report should prefer prepared-scene artifacts over directory scans or ad hoc mesh discovery.
- Prepared-scene artifacts are UI/runtime acceleration metadata, but they still require explicit source-artifact provenance and coordinate-frame labeling.

## Measurement Export Bundles

Measurement-side export bundles are now written to an explicit user-selected destination rather than a fixed case-owned `analytics\exports` location.

Current bundle layout:

- `baseline-meshes/`
- `standing-scene/`
- `standing-inputs/`
- `standing-drrs/`
- `measurements/`
- `artifacts/`
- `bundle_manifest.json`

Rules:

- Export bundles are user-facing deliverables, not pipeline-stage caches.
- They may copy stage artifacts and source review inputs, but must not become the canonical source of truth for the pipeline.
- The current `standing-drrs/` outputs are explicitly scaffold mesh projections.
- Do not label those scaffold images as true volume-integral DRRs in downstream clinical logic or reports.
- When the NanoDRR stage lands, it should replace the scaffold generation mode while preserving the same top-level bundle contract.

### `bundle_manifest.json`

Should include:

- bundle creation timestamp
- case ID
- source measurement artifact IDs
- exported mesh and scene relative paths
- exported report and measurement relative paths
- `segmentation_backend` provenance block with:
  - `backend_id`
  - `display_name`
  - `family`
  - `driver_id`
  - `runtime_environment_id`
  - `checkpoint_id`
  - `model_name`
  - `model_version`

Rules:

- Export bundles must preserve enough segmentation-backend provenance to distinguish different backend renders or downstream review packages.
- Export-bundle naming should include the backend slug when provenance is available so repeated exports from different backends do not overwrite or become ambiguous.

### `landmarks.json`

Should include:

- vertebral level
- structure instance ID
- landmark name
- coordinates
- coordinate frame
- confidence
- model version
- supporting geometry IDs

### `pose_graph.json`

Should include:

- vertebral nodes
- parent or adjacency structure
- rigid transforms
- transform source and target frames
- uncertainty
- registration objective summary
- image IDs used
- calibration status

### `measurements.json`

Should include:

- metric name
- value
- units
- definition version
- measurement mode
- coordinate frame
- projected or native-3D flag
- confidence interval or uncertainty
- required primitives
- validity flag
- invalidity reason when invalid
- source artifact IDs

Current mode requirements:

- The first production measurement slice is `single_pose_native_3d`.
- Single-pose native metrics may include disc height, listhesis, segmental lordosis or kyphosis, lumbar lordosis, and thoracic kyphosis when their required primitives are present.
- Unsupported radiograph-equivalent or field-of-view-limited metrics must remain explicit invalid records rather than being omitted or back-filled with placeholders.

## Current Repo Mapping

The current repo already has a case manifest and stage artifact scaffolding in:

- [src/spinelab/models/manifest.py](/D:/claude/spinelab/src/spinelab/models/manifest.py)
- [src/spinelab/pipeline/artifacts.py](/D:/claude/spinelab/src/spinelab/pipeline/artifacts.py)
- [src/spinelab/pipeline/contracts.py](/D:/claude/spinelab/src/spinelab/pipeline/contracts.py)

Those structures are still an interim product shell. They should evolve toward the contract fields above rather than becoming the permanent schema by accident.

## Implementation Guidance

- Add contract files as stage-owned artifacts under the active session `analytics/derived/` tree so they can be packaged into `.spine` on save.
- Do not overload UI-only manifest fields with clinical geometry contracts.
- When a schema changes, version it and update the brief, manifesto, and any affected code paths together.
