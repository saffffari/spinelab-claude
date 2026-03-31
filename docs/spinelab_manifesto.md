# SpineLab Manifesto
**Version:** 0.1  
**Date:** 2026-03-23  
**Status:** Living manifesto / canonical long-form project brief  
**Audience:** new agents, engineers, researchers, clinical collaborators

---

## 1. What SpineLab is

SpineLab is an articulated-spine modeling and measurement platform whose core goal is to recover **patient-specific 3D vertebral pose and motion from sparse 2D imaging** by combining:

1. a preoperative or baseline **3D CT or MRI** that provides subject-specific anatomy,
2. a different patient pose captured by **biplanar EOS radiographs** or **two or more calibrated C-arm X-rays**, and
3. a **polyrigid / articulated registration layer** that transforms the 3D anatomy into the new pose so measurements can be made in 3D rather than only in 2D.

The immediate scientific product is a **3D-3D vertebral motion and alignment measurement engine**.  
The longer-term clinical product is an **intraoperative and perioperative spine visualization, planning, and measurement system** that can support deformity analysis, alignment assessment, pedicle planning, and eventually broader musculoskeletal or multimodal planning.

This document is the canonical context for new agents. If something here conflicts with ad hoc notes elsewhere, this document wins unless a clinician explicitly supersedes it.

---

## 2. Executive summary

### 2.1 North-star objective
Build a system that can take a patient’s preoperative CT/MRI-derived 3D skeletal geometry and infer its pose in a new posture from sparse 2D X-rays, then compute clinically meaningful spinal and spinopelvic measurements with uncertainty estimates and interactive visualization.

### 2.2 Practical first product
The first product should not be “a giant all-in-one AI.” It should be a **modular, clinically auditable pipeline**:

- ingest DICOM + metadata + calibration
- segment and label vertebrae (and later pelvis/femurs and more anatomy)
- extract meshes / surfaces
- label vertebral substructures and landmarks
- solve sparse-view 2D/3D registration with an articulated prior
- compute measurements from a versioned measurement engine
- display results in the existing GUI
- expose uncertainty, QC flags, and manual edit points

### 2.3 Current best technical stance
Given current evidence, the safest starting point is:

- **Segmentation:** use the **nnU-Net ecosystem** as the backbone, with **Residual Encoder nnU-Net** as the safest default and **MedNeXt-L** as the high-accuracy aggressive option; use **TotalSegmentator** / **TotalSegmentator MRI** as a broad, practical bootstrap rather than the final answer for all spine tasks. The broader benchmarking literature still favors carefully tuned CNN-based nnU-Net derivatives over many transformer-only alternatives for 3D medical segmentation. [R1][R2][R3][R4][R5][R6]
- **Vertebral shape / landmark modeling:** do **dense point segmentation plus dense correspondence**, not generic whole-object classification. A hierarchical local-global point model with self-supervised pretraining and a correspondence head is the right default research direction. [R8][R9][R10][R11][R12][R13]
- **Sparse-view pose recovery:** build around **PolyPose-style polyrigid 2D/3D registration**, because the spine is better modeled as a chain of rigid bones connected by deformable joints than as a single deformable blob. PolyPose is especially relevant because it is explicitly designed for sparse-view, limited-angle X-ray settings and uses the biologically meaningful prior that bones do not bend. [R14]
- **Clinical measurement:** compute both:
  - **radiograph-equivalent values** that match standard clinical definitions and enable comparison to legacy workflows, and
  - **native 3D values** that exploit the posed 3D model.
- **QC / trust:** every stage must emit uncertainty and failure flags. The system must fail closed, not hallucinate clean answers from low-quality inputs.

### 2.4 Central warning
The requested **1 mm target** is a good aspirational benchmark for **local bony landmark error** under good imaging and calibration. It should **not** be treated as an unconditional promise for every end-to-end global alignment metric in standing-vs-supine or intraoperative sparse-view scenarios. The biggest gap is not just model accuracy; it is **calibration, posture mismatch, imaging completeness, and clinical definition drift**.

---

## 3. Scope, assumptions, and non-negotiables

## 3.1 Working assumptions
Plan as if the project can access:

- Cedars-Sinai Epic-linked clinical data
- PACS/DICOM imaging archives
- radiology reports
- operative notes
- implant logs / device metadata where available
- diagnosis and procedure codes
- longitudinal follow-up imaging
- surgeon measurements where available
- enough annotation resources to build high-quality internal gold standards

Also assume that data volume is not the main bottleneck. If something needs a larger dataset, the project should prefer building the dataset over prematurely constraining the modeling approach.

## 3.2 Project boundaries
### In scope now
- spine CT/MRI segmentation and vertebra labeling
- bone mesh generation
- vertebral substructure and landmark labeling
- 2D/3D pose recovery from EOS or multi-view C-arm
- 3D measurement engine
- GUI integration
- uncertainty / QC
- benchmark design and validation

### In scope later
- full skeleton and extra organs
- neural / disc / ligament soft tissue modeling
- pedicle screw planning
- synthetic CT from MRI
- intraoperative assistance and navigation support
- outcome prediction using Epic-linked longitudinal data

### Explicitly not the first focus
- pure soft-tissue neuro-compression diagnosis from shape alone
- unsupervised end-to-end black-box “one model solves everything”
- chasing the newest architecture without a validation case
- hiding failure states from clinicians

## 3.3 Non-negotiables
1. **Measurement definitions are versioned.** Do not silently redefine a metric.
2. **Every output has provenance.** A measurement should always be traceable to source images, segmentations, landmarks, and transforms.
3. **Every module exposes confidence / uncertainty.**
4. **Patient-level data splitting only.** No leakage across studies, time points, or modalities for the same patient.
5. **Clinical usability matters as much as benchmark performance.**
6. **The system must support manual correction.**
7. **Radiograph-equivalent and true-3D measurements must be kept distinct.**

---

## 4. Product vision

SpineLab should eventually act as a **patient-specific spine digital twin system** with three linked tracks.

### Track A: research-grade motion and deformity quantification
- quantify vertebral motion between postures or time points
- characterize segmental and global alignment
- provide high-fidelity, reproducible 3D metrics
- compare 2D clinical metrics against 3D equivalents

### Track B: perioperative / intraoperative visualization
- align preoperative CT/MRI anatomy to intraoperative EOS or fluoroscopy
- provide live or near-live visualization of spinal alignment and vertebral orientation
- support measurement during surgery without requiring a full intraoperative CT

### Track C: planning and safety augmentation
- pedicle and posterior element morphometry
- pedicle-safe corridor estimation
- hardware trajectory planning support
- implant/alignment comparison across time
- revision and complication surveillance

A strong design principle is that Track A should produce the validated substrate for Tracks B and C.

---

## 5. Canonical system architecture

## 5.1 Conceptual pipeline

```text
CT/MRI volume
  -> segmentation + vertebra instance labeling
  -> mesh/surface extraction
  -> vertebral substructure + landmark inference
  -> canonical vertebral frames + subject-specific articulated spine graph
  -> sparse-view EOS / C-arm ingestion + geometry calibration
  -> polyrigid 2D/3D registration / pose recovery
  -> posed 3D spine model
  -> 3D measurement engine
  -> uncertainty / QC / manual corrections
  -> GUI visualization + export + analytics
```

## 5.2 Recommended module decomposition

### Module 1 — data ingestion and normalization
Responsibilities:
- DICOM import
- image resampling and orientation normalization
- metadata extraction
- scanner geometry parsing
- C-arm / EOS calibration handling
- patient/study/series linkage
- Epic/PACS longitudinal indexing

Key design rule:
- store raw image data and metadata unchanged, then derive normalized representations without destroying the original provenance.

### Module 2 — volumetric segmentation and vertebra instance labeling
Responsibilities:
- bone segmentation
- vertebral instance separation
- vertebral level labeling
- sacrum / pelvis / femoral head segmentation when present
- optional disc / canal / ligament / soft tissue segmentation later

### Module 3 — surface generation
Responsibilities:
- convert segmentation masks to meshes / surfaces / point clouds
- preserve watertight geometry where possible
- maintain mapping between voxel space and surface space
- support decimation for inference while retaining a high-resolution version for visualization and measurement

### Module 4 — vertebral substructure and landmark inference
Responsibilities:
- per-vertebra or whole-spine landmark detection
- substructure segmentation
- endplate and posterior wall estimation
- pedicle and posterior element localization
- correspondence learning to an atlas / statistical shape model

### Module 5 — articulated pose model and sparse-view registration
Responsibilities:
- represent vertebrae and pelvis as rigid bodies
- represent discs / joints as constrained degrees of freedom
- estimate global camera geometry
- estimate per-vertebra rigid transforms in a new posture
- regularize with anatomical chain constraints

### Module 6 — measurement engine
Responsibilities:
- compute versioned local, regional, and global metrics
- compute both projected and true-3D variants where applicable
- support confidence intervals and QC flags
- store intermediate geometric primitives (planes, centers, lines, axes)

### Module 7 — GUI / interaction layer
Responsibilities:
- overlay anatomy, landmarks, and measurements
- visualize uncertainty and failure modes
- allow manual corrections
- record edits as training data

### Module 8 — data flywheel
Responsibilities:
- active learning
- annotation queueing
- difficult-case mining
- continuous benchmarking
- drift detection across scanners, protocols, and diagnoses

---

## 6. Recommended initial technical stack

## 6.1 Segmentation strategy

### Core recommendation
Use a **two-lane segmentation strategy**:

#### Lane A: practical bootstrap lane
- **CT:** TotalSegmentator for broad initial anatomy coverage, quick prototyping, dataset bootstrapping, and pseudo-label generation. TotalSegmentator was trained on 1204 CT exams and segments 104 structures with strong reported performance on diverse clinical data. [R3]
- **MRI:** TotalSegmentator MRI and/or MRAnnotator / MRSegmentator for initial bootstrapping depending on field of view and available sequence types. TotalSegmentator MRI segments 80 structures and reported good sequence-independent performance; MRAnnotator is very strong when its 44-label set matches the task; AbdoBench found MRSegmentator to be the best-performing and most generalizable among the evaluated open-source abdominal MRI models. [R4][R5][R6]

Use this lane to:
- get early end-to-end demos running
- generate initial masks for annotation refinement
- stand up the GUI and downstream measurement flow quickly

#### Lane B: SpineLab-specific high-accuracy lane
Train custom internal models on Cedars data.

Recommended starting point:
- **Residual Encoder nnU-Net (ResEnc-L where feasible)** as the safest default, because the official nnU-Net docs now recommend ResEnc-L as the new default configuration and the broader benchmark still found the nnU-Net/CNN family strongest overall. [R1][R2]
- **MedNeXt-L** as the high-accuracy challenger when compute and training time are acceptable. [R1][R2]
- **FMC-Net** as a research-track vertebra specialist worth evaluating, but not yet the only foundation to trust without strong internal validation. FMC-Net reports strong results on VerSe2019 CT and LUMBAR MRI. [R7]

### Practical recommendation by modality
- **CT full-spine / bones:** Start with TotalSegmentator bootstrap, then train custom ResEnc nnU-Net, with MedNeXt-L as a challenger model.
- **MRI spine:** use MRAnnotator / TotalSegmentator MRI / MRSegmentator for bootstrapping, then train a custom spine-specific nnU-Net family model on Cedars data.
- **Final product:** do not assume an off-the-shelf general model will be the final answer. The final product should almost certainly use a **custom SpineLab-trained model**.

### Why this is the right compromise
The project needs:
- accuracy
- interpretability
- repeatability
- broad modality coverage
- fast iteration

The nnU-Net ecosystem is still the best practical base for that combination. [R1][R2]

## 6.2 Mesh and surface generation
Recommended default:
- triangles as the canonical stored/exported mesh type
- discrete flying edges for the default per-vertebra extractor
- surface nets as the benchmarked alternate when shared-boundary multi-label extraction is needed
- topology-preserving smoothing
- mesh cleanup with explicit component checks
- consistent vertex normal computation
- point-cloud sampling from surfaces for point-based models
- retain an undegraded “measurement mesh” and a lighter “inference mesh”

Important rule:
- **measurement should happen on a high-fidelity geometry**, not only on the aggressively downsampled point cloud used for learning.

## 6.3 Vertebral landmark and substructure modeling

### Core recommendation
Treat this as **dense point segmentation + landmark regression + correspondence learning**, not object classification.

Recommended default design:
- hierarchical local-global encoder-decoder
- canonicalized vertebral input frame
- multi-task heads for:
  - substructure labels
  - landmark coordinates
  - endplate / posterior wall planes
  - correspondence points to an atlas or shape model
  - uncertainty

Suggested model ingredients:
- PointNeXt-style training discipline and scaling mindset [R8]
- Point-MAE-style self-supervised pretraining on unlabeled vertebral surfaces [R9]
- DAFNet-like local-global geometry modeling as an architectural inspiration, not necessarily the only candidate [R10]
- Point2SSM++-style correspondence learning for semantically consistent shape points [R11]

### Why canonicalization matters
A single vertebra network has a much easier job if the vertebra is first normalized into a consistent anatomical frame. This reduces irrelevant pose variance and lets the network focus on shape.

Recommended canonicalization anchors:
- superior and inferior endplates
- left and right pedicle roots / centers
- vertebral level conditioning (C/T/L/S)

### New design recommendation
Use a **three-head vertebra model**:
1. **part segmentation head** for substructures
2. **landmark/plane regression head** for direct measurements
3. **correspondence head** to an atlas / SSM

This is better than a single monolithic output because the three outputs constrain each other:
- parts make landmarks more stable
- landmarks make planes and frames more stable
- correspondence makes the system anatomically consistent across patients and pathologies

## 6.4 Registration / pose recovery
The core registration layer should be **polyrigid / articulated**, not generic dense deformation.

Why:
- individual vertebrae are rigid
- discs and joint spaces deform
- sparse-view X-rays underdetermine dense deformations
- anatomical plausibility matters more than arbitrary warp flexibility

PolyPose is highly relevant because it was developed exactly for sparse-view deformable 2D/3D registration, parameterizes deformation as a composition of rigid transforms, and succeeds with as few as two X-rays in limited-angle settings. [R14]

### SpineLab adaptation of the PolyPose idea
Represent the spine as:
- rigid bodies: each vertebra + sacrum + optionally pelvis
- constrained joints: discs / facet interactions / spinopelvic connections
- weights / influence fields that define locally rigid warps
- optional learned priors for level-specific motion plausibility

### Strong recommendation
Do **not** try to register the entire spine as one rigid body. That will fail whenever the posture change contains meaningful segmental motion.

### Strong recommendation #2
Do **not** allow a totally free dense warp without articulated constraints in sparse-view settings. It is too ill-posed and will produce plausible-looking nonsense.

---

## 7. Project-defining anatomical ontology

The project should use a **tiered ontology**. This prevents over-annotation early while keeping the design extensible.

## 7.1 Tier 1 — core measurement anatomy (mandatory)
For each vertebra from at least **C7–S1** for the minimum measurement package, but ideally **C2/C1–S1** for the full system:

- vertebral body
- superior endplate surface
- inferior endplate surface
- posterior vertebral body wall
- anterior-superior corner
- posterior-superior corner
- anterior-inferior corner
- posterior-inferior corner
- superior endplate midpoint
- inferior endplate midpoint
- vertebral body centroid / center
- midsagittal vertebral plane
- midcoronal vertebral plane

These are the core landmarks for disc height, disc angle, listhesis, regional lordosis/kyphosis, Cobb measurements, SVA, and coronal balance.

## 7.2 Tier 2 — sacropelvic and global balance anatomy (mandatory for full alignment)
- S1 superior endplate surface
- midpoint of S1 superior endplate
- posterior-superior corner of S1
- sacral midline / sacral center
- left femoral head center
- right femoral head center
- bicoxofemoral axis / hip axis midpoint
- C7 vertebral body center

Without these, PI/PT/SS and global balance are not standard-computable.

## 7.3 Tier 3 — deformity planning anatomy (strongly recommended)
- end vertebrae of each curve
- apical vertebra
- stable vertebra
- neutral vertebra
- vertebral rotation descriptors
- coronal and axial reference axes

## 7.4 Tier 4 — degenerative surgery planning anatomy (strongly recommended for the next phase)
- pedicles (left/right)
- pedicle centers / pedicle corridors
- laminae
- spinous process
- transverse processes
- superior and inferior articular processes / facet surfaces
- pars interarticularis
- vertebral canal boundary
- foraminal roof / floor / boundaries
- intervertebral discs
- ligamentum flavum
- dural sac
- nerve roots (future MRI-rich branch)

### Critical note
For the **current measurement package**, Tier 1 + Tier 2 are enough to build a valid first measurement engine.  
For **actual spine surgery planning**, Tier 4 becomes important very quickly.

---

## 8. Measurement specification (house conventions)

SpineLab should freeze and version the measurement definitions now. This will save enormous pain later.

## 8.1 Principle: projected vs native-3D metrics
For each clinically recognized metric, SpineLab should store:

- **Projected / radiograph-equivalent metric**
  - computed from the posed 3D model after projection into the clinically relevant plane
  - designed to match standard radiographic definitions

- **Native 3D metric**
  - computed directly on the 3D posed anatomy
  - used for research and potentially better biomechanical interpretation

This dual representation is one of the best ways to gain clinical trust while still advancing the science.

## 8.2 Core measurements to support

### Local / disc level
- anterior, middle, posterior disc height
- disc midpoint height
- disc space angle
- spondylolisthesis / retrolisthesis (posterior wall referenced)
- segmental lordosis / kyphosis

### Regional sagittal
- lumbar lordosis (default house convention: L1 superior to S1 superior)
- thoracic kyphosis (default house convention: T4 superior to T12 inferior)
- thoracolumbar junction kyphosis (default house convention: T10 superior to L2 inferior)
- apex of lordosis (must be definition-versioned)

### Spinopelvic
- pelvic incidence
- pelvic tilt
- sacral slope

### Global sagittal / coronal
- SVA
- coronal balance / C7-CSVL distance
- scoliosis Cobb angles for PT, MT, TL/L curves
- vertebral rotation descriptors when available

## 8.3 Measurements and required primitives

### Disc height
Needed:
- inferior endplate of cranial vertebra
- superior endplate of caudal vertebra
- disc centerline or disc midpoint

Recommendation:
- store anterior, middle, posterior heights, not just one central number.

### Listhesis
Needed:
- posterior vertebral wall or posterior body corners of adjacent levels

Recommendation:
- define translation in a segment-specific coordinate frame, not only global AP space.

### Disc space angle
Needed:
- inferior endplate plane of upper vertebra
- superior endplate plane of lower vertebra

### Pelvic incidence / tilt / sacral slope
Needed:
- S1 superior endplate plane and midpoint
- bilateral femoral head centers / hip axis
- vertical and horizontal references where appropriate

### Lumbar lordosis
Needed:
- superior endplate of L1
- superior endplate of S1

### Segmental lordosis
Needed:
- chosen bounding endplates of the segment

Important:
- decide now whether any nonstandard convention (e.g. bottom of S1) will ever be used. If yes, version it. Do not silently switch conventions later.

### Apex of lordosis
Needed:
- a curve-based definition, not a casual heuristic

Recommendation:
- define this as the vertebral level or spline location with maximal anterior deviation from a reference line in the sagittal plane and version the exact procedure.

### Thoracic kyphosis
Needed:
- default T4 superior and T12 inferior endplates unless a different clinic-specific convention is adopted

### SVA
Needed:
- C7 center
- vertical plumb line
- posterior-superior S1 corner

### Coronal balance
Needed:
- C7 center
- sacral midline / CSVL

### Scoliosis Cobb angles
Needed:
- endplate planes across the entire curve region
- end vertebra selection logic
- apical vertebra identification

---

## 9. Canonical coordinate systems and transforms

This needs to be designed before implementation gets messy.

## 9.1 Recommended spaces
Maintain explicit transforms between:

1. **Native image space**
   - original DICOM voxel geometry and orientation

2. **Normalized volume space**
   - resampled and orientation-normalized volume

3. **Surface / mesh space**
   - derived from the segmented volume

4. **Vertebra local anatomical frame**
   - per-vertebra frame for substructure and motion analysis

5. **Patient body frame**
   - common 3D frame for the whole posed anatomy

6. **Imaging system frame**
   - EOS / C-arm geometry

7. **Display frame**
   - GUI visualization frame

## 9.2 Proposed vertebral local frame
Recommended initial definition:

- origin: vertebral body centroid or midpoint between superior and inferior endplate midpoints
- superior-inferior axis: mean endplate normal / endplate-center axis
- left-right axis: pedicle-center axis
- anterior-posterior axis: cross product completing a right-handed anatomical frame

This should be refined and clinically reviewed, but the project should absolutely have a canonical vertebral frame early. Too many downstream bugs come from silent frame inconsistencies.

## 9.3 Transform bookkeeping
Every measurement should be reproducible from:
- source volume ID
- segmentation version
- mesh version
- landmark model version
- registration version
- measurement version
- relevant transforms

Treat transform provenance as first-class project infrastructure, not a logging afterthought.

---

## 10. Data strategy under the Cedars/Epic assumption

The project should exploit the assumption of broad data access aggressively and intelligently.

## 10.1 Data categories to prioritize
### Imaging
- preoperative CT
- preoperative MRI
- standing long-cassette radiographs
- EOS biplanar images and any vendor-derived reconstructions if available
- intraoperative fluoroscopy / C-arm images
- postoperative CT where clinically obtained
- follow-up radiographs / EOS / MRI

### Clinical metadata
- operative episode linkage
- diagnosis and procedure codes
- surgeon service / subspecialty
- implant information
- revision surgery occurrence
- adverse events / complications
- radiology reports
- operative notes
- clinic notes
- patient-reported outcomes if available (ODI, VAS, PROMIS, SRS-22, etc.)

### Technical metadata
- scanner make/model
- protocol
- voxel spacing
- C-arm geometry / projection metadata
- EOS acquisition type
- timing relative to surgery and posture

## 10.2 Cohort design
Build at least four cohorts:

### Cohort A — segmentation and landmark cohort
Purpose:
- train and validate segmentation, labeling, and substructure models

Ideal contents:
- full-spine CT/MRI
- broad pathology diversity
- metal and non-metal cases
- pediatric and adult subcohorts if relevant

### Cohort B — cross-modal posture cohort
Purpose:
- train and validate 2D/3D registration and measurement transfer

Ideal contents:
- same-patient CT/MRI plus standing EOS or long-cassette X-rays
- same-day or short-interval pairs where possible
- full field of view including hips and C7 when global measurements are needed

### Cohort C — intraoperative cohort
Purpose:
- C-arm pose recovery and surgical workflow testing

Ideal contents:
- preoperative CT/MRI
- calibrated intraoperative C-arm images from multiple views
- operative notes
- navigation logs if available
- postop confirmation imaging where clinically obtained

### Cohort D — longitudinal outcome cohort
Purpose:
- correlate geometry/motion/alignment with outcomes and complications

Ideal contents:
- repeated imaging across time
- symptom scores
- revision / reoperation labels
- hardware failure / junctional pathology labels

## 10.3 Labeling strategy
Use a **gold / silver / bronze** labeling hierarchy.

### Gold labels
- expert-reviewed vertebral segmentations
- exact landmark annotations
- measurement adjudications
- calibration-verified registration reference cases

### Silver labels
- high-confidence pseudo-labels from TotalSegmentator, MRAnnotator, custom models, and vendor tools with human review

### Bronze labels
- weak labels from reports, billing codes, procedure metadata, and heuristics

## 10.4 Active learning recommendation
The GUI should double as an annotation correction interface.  
Every manual correction should become training data.

Best candidates for active learning:
- transitional anatomy
- severe scoliosis / kyphosis
- osteophytes
- burst/compression fractures
- metastatic destruction
- postoperative hardware
- poor MRI bone contrast
- partial field of view
- rib-vertebra confusion zones

---

## 11. Benchmarking and evaluation plan

A project like this fails if it only reports Dice.

## 11.1 Segmentation benchmarks
Measure:
- Dice
- HD95
- vertebra instance separation accuracy
- vertebral level labeling accuracy
- robustness by region (cervical, thoracic, lumbar, sacrum)
- robustness by pathology
- robustness by metal artifact
- robustness by scanner / protocol / site

Public anchors:
- VerSe for vertebra segmentation/labeling; VerSe also includes fracture grading metadata that can support downstream tasks. [R19]

## 11.2 Landmark and substructure benchmarks
Measure:
- mean absolute landmark error (mm)
- 95th percentile landmark error
- plane normal angular error (degrees)
- point-to-surface distance for correspondence points
- pedicle center error
- endplate center error

Important:
- benchmark per vertebral level, not only pooled.

## 11.3 Registration / pose benchmarks
Measure:
- per-vertebra translation error
- per-vertebra rotation error
- reprojection error in image space
- downstream measurement error induced by registration
- failure rate in limited-angle sparse-view settings

Where possible, benchmark on:
- phantoms
- same-patient near-timepoint imaging
- clinically acquired paired data
- synthetic DRR experiments with known transforms

## 11.4 Measurement benchmarks
Measure:
- absolute error versus expert
- ICC
- Bland–Altman agreement
- test-retest reproducibility
- inter-rater and intra-rater comparison
- robustness to small perturbations in landmarks / registration

Key point:
- the clinical win is not only average accuracy; it is **reliability and failure awareness**.

## 11.5 Workflow benchmarks
Measure:
- inference latency
- total time-to-result
- manual correction time
- percentage of cases that pass QC without manual intervention
- percentage of failures caught by QC

## 11.6 Proposed internal gate criteria
These are project gates, not promises to publications.

### Gate 1 — CT geometry foundation
- high vertebra segmentation quality
- stable instance labeling
- local landmark error approaching 1 mm in curated internal test cases

### Gate 2 — measurement validity on 3D static geometry
- measurement engine matches expert-derived values on CT/EOS-reference datasets

### Gate 3 — EOS posture transfer
- global and segmental measurements remain clinically acceptable after sparse-view pose recovery

### Gate 4 — C-arm/intraoperative feasibility
- acceptable latency
- consistent registration under real intraoperative imaging variation
- trustworthy QC / fallback behavior

---

## 12. Critical risks and likely failure modes

This section matters as much as the architecture.

| Risk | Why it matters | Mitigation |
|---|---|---|
| Standing vs supine mismatch | CT/MRI are often non-weight-bearing while EOS is standing; discs and soft tissues truly deform | use articulated vertebral chain, not global rigid registration; stratify by posture; build standing-reference cohorts |
| Missing field of view | PI/PT/SS need femoral heads; SVA/CVA need C7 and sacrum; local CT/MRI often miss them | QC completeness checker; metric availability logic; do not compute metrics that are unsupported by the FOV |
| C-arm geometry / calibration errors | sparse-view registration can look plausible but be wrong | preserve and validate projection metadata; phantom-based calibration checks; reprojection QC |
| Rib/vertebra confusion and transitional anatomy | can corrupt instance labels and measurements | thoracic QC, vertebral numbering logic, anomaly flags, targeted data enrichment |
| Metal artifact and postoperative anatomy | segmentation and registration degrade sharply | artifact-aware training, hardware-specific cohorts, fail-closed behavior |
| Definition drift | different teams may compute slightly different Cobb/lordosis/listhesis values | measurement versioning and locked house conventions |
| Error propagation | small upstream errors can create large metric errors | propagate uncertainty; retain intermediate primitives; measure sensitivity |
| Over-trusting shape alone | soft tissue stenosis, marrow disease, epidural pathology are not surface-shape problems | add image branch for CT/MRI appearance; keep shape and appearance branches distinct |
| Dataset leakage | same patient may appear across multiple modalities/timepoints | strict patient-level split logic |
| Domain shift | scanners, protocols, sequence types, postures, age groups vary | diverse internal training; external validation; drift monitoring |
| Latency and workflow burden | great offline models that are too slow or fragile will not survive clinic | optimize later, but track time-to-result from day one |
| Regulatory / trust barrier | black-box outputs without editability will not be used | uncertainty, provenance, overlays, manual correction pathway |

### Important scientific warning
The biggest conceptual danger is to pretend the posture change is “just registration.” It is actually a mixed problem involving:
- rigid bony motion
- intervertebral deformation
- posture-dependent global balance
- partial observability from 2D projection
- clinically defined measurements that were historically designed for radiographs

SpineLab should embrace that complexity instead of hiding it.

---

## 13. New ideas and underexplored opportunities

This section intentionally goes beyond the current plan.

## 13.1 Build an articulated spine graph, not only a mesh
Represent the spine as a graph:
- nodes = vertebrae, sacrum, pelvis
- edges = discs / facet-linked joints
- attributes = level, planes, centers, motion priors, uncertainty

This can unify segmentation, registration, and measurement in a single data structure and will likely simplify both debugging and biomechanical interpretation.

## 13.2 Treat discs as deformable joints explicitly
A pure polyrigid model is better than a global warp, but it still misses disc behavior.  
Add a small learned or parametric **joint deformation layer** between vertebrae:
- compressive opening/closing
- wedge changes
- constrained translations
- limited axial rotation

This is a strong candidate for improving posture transfer realism.

## 13.3 Use differentiable rendering for cycle consistency
For EOS / C-arm registration, enforce:
- 3D -> projected 2D consistency
- multi-view consistency
- cycle consistency across repeated views / time points

This may make the registration branch more stable without requiring dense labels for every view.

## 13.4 Ask the system which next X-ray view is best
A high-value intraoperative feature:
- given current uncertainty, recommend the next C-arm angle that most reduces ambiguity

That is a real clinical systems idea, not just a model improvement.

## 13.5 Output uncertainty on measurements, not only on masks
Surgeons care about whether a number is trustworthy.  
Report:
- measurement mean
- confidence interval
- quality flag
- reasons for degraded confidence

Example:
- “PI = 51.2° ± 1.4°, confidence high”
- “SVA unavailable: C7 outside field of view”
- “L4–L5 listhesis uncertain: posterior wall confidence low due to hardware artifact”

## 13.6 Build a normative atlas layer
With enough data, SpineLab can learn:
- vertebra-level normative morphology
- age/sex/body habitus-adjusted alignment distributions
- pathology-conditioned outlier detection

This could support:
- fracture and deformity detection
- pre-op risk stratification
- hardware planning personalization

## 13.7 Use synthetic CT / CT-like MRI as a strategic branch
The literature around MRI-based synthetic CT and CT-like MRI for spine planning is moving quickly, including evidence that deep-learning reconstructed lumbar MRI can support virtual pedicle planning and that MRI-derived synthetic CT may support planning and navigation in some settings. [R17][R18]
SpineLab should not make this the phase-1 dependency, but it should absolutely maintain compatibility with an MRI-to-CT-like branch because it could reduce radiation and broaden use cases.

## 13.8 Keep a dedicated image branch
Point clouds and surfaces are excellent for outer geometry, but many clinically important neuro-spine findings live in image appearance.  
The long-term model should be **multimodal**:
- shape branch
- image branch
- multi-vertebra context branch

## 13.9 Learn measurement primitives directly
Instead of only deriving everything from full segmentation, consider training dedicated heads for:
- endplate planes
- posterior wall lines
- femoral head centers
- sacral midpoint
- C7 center

This may outperform a pure “segment everything then derive later” pipeline on the most clinically important primitives.

## 13.10 Build a data flywheel around corrections
A huge advantage of your existing GUI is that it can become the capture tool for:
- manual landmark fixes
- vertebral renumbering
- pedicle edits
- invalid-metric flags
- measure acceptance / rejection

This makes the interface itself part of the model improvement system.

---

## 14. Recommended phased roadmap

## Phase 0 — specification and infrastructure
Deliverables:
- this manifesto plus the layered operational docs
- AGENTS.md pointer
- data contracts
- transform conventions
- metric definitions
- benchmark design
- artifact/versioning plan

## Phase 1 — CT foundation
Goals:
- robust CT spine/pelvis/femoral-head segmentation
- vertebra instance labeling
- mesh generation
- Tier 1 and Tier 2 landmarks
- measurement engine on 3D CT geometry

Recommended starting choices:
- TotalSegmentator bootstrap + custom ResEnc nnU-Net baseline
- MedNeXt challenger
- measurement engine before registration

Success condition:
- you can compute clinically sensible static 3D measurements on CT-derived anatomy and inspect them in the GUI.

## Phase 2 — MRI foundation
Goals:
- bone-capable MRI pipeline
- custom spine MRI segmentation
- MRI landmark transfer to CT-compatible geometry
- assess where MRI alone is sufficient and where synthetic CT is needed

Recommended starting choices:
- bootstrap with MRAnnotator / MRSegmentator / TotalSegmentator MRI
- build a spine-specific custom model

## Phase 3 — vertebral substructures and correspondence
Goals:
- part segmentation
- endplate / pedicle / lamina / posterior element localization
- canonical local frames
- atlas correspondence

Recommended choices:
- Point-MAE pretraining
- PointNeXt/DAFNet-style hierarchical segmentation backbone
- Point2SSM++-style correspondence branch

## Phase 4 — EOS posture transfer
Goals:
- calibrated EOS ingestion
- AP/lateral sparse-view pose recovery
- global and segmental measurement validation

Recommended choices:
- PolyPose-inspired articulated registration
- measurement uncertainty propagation
- explicit completeness checks

## Phase 5 — C-arm / intraoperative integration
Goals:
- limited-angle registration
- latency optimization
- clinical UI design for intraop use
- screw-planning pilot features

## Phase 6 — clinical validation and productization
Goals:
- reliability studies
- clinical workflow studies
- outcome linkage
- internal pilot deployment

---

## 15. Suggested experiments that should happen early

1. **CT-only measurement validation**
   - Build measurement engine before registration.
   - This isolates geometry/landmark issues from pose issues.

2. **Bootstrap vs custom segmentation bake-off**
   - Compare TotalSegmentator and custom ResEnc nnU-Net on internal spine tasks.
   - Do not assume the public model is good enough in thoracic/transitional/post-op cases.

3. **Per-vertebra pose recovery rather than whole-spine rigid registration**
   - Demonstrate that segmental motion is actually recoverable and matters.

4. **Landmark-first vs segmentation-first experiment**
   - For a subset of metrics, test direct landmark prediction against derivation from full segmentation.

5. **Supine-to-standing domain study**
   - Quantify which errors are due to segmentation and which are due to genuine posture-induced anatomical change.

6. **Human factors test in the GUI**
   - Identify which visualizations and manual edit tools are actually useful to clinicians.

---

## 16. Current recommended decisions

These are the current “best default” decisions unless a future benchmark clearly beats them.

### Decision 1
**Use a layered documentation stack plus AGENTS.md pointers.**  
Keep a long-form manifesto for context and rationale, but use shorter operational docs for onboarding, contracts, and measurement rules so routine implementation work does not require loading the entire project brief.

### Decision 2
**Segmentation default = custom ResEnc nnU-Net baseline.**  
Use TotalSegmentator / MR models only as bootstrap and comparison tools.

### Decision 3
**Point cloud default = dense segmentation + correspondence model.**  
Do not frame vertebral substructure labeling as generic classification.

### Decision 4
**Registration default = PolyPose-style articulated / polyrigid model.**

### Decision 5
**Measurement engine is a first-class module, not an afterthought.**

### Decision 6
**QC and uncertainty are required deliverables for every module.**

### Decision 7
**Use the GUI as both visualization layer and data improvement layer.**

---

## 17. Things that should not be forgotten

- Global metrics are impossible without the right field of view.
- Spine measurements are definition-sensitive.
- A pretty overlay can still be geometrically wrong.
- The most dangerous failures are confident wrong answers that look smooth.
- Post-op / hardware / transitional anatomy cases must be included early, not as an afterthought.
- Distinguish “can be computed” from “should be trusted.”
- The project’s real moat is not one network; it is the combination of:
  - strong data
  - clinically correct definitions
  - articulated registration
  - uncertainty-aware measurement
  - usable workflow integration

---

## 18. Immediate next implementation tasks

1. Freeze metric definitions and coordinate conventions.
2. Define a JSON/YAML data contract for:
   - segmentation outputs
   - mesh outputs
   - landmarks
   - per-vertebra transforms
   - measurement outputs
3. Stand up CT baseline:
   - TotalSegmentator bootstrap
   - custom ResEnc nnU-Net training pipeline
4. Implement mesh/point-cloud generation with provenance.
5. Implement Tier 1 + Tier 2 measurement engine independent of registration.
6. Define EOS / C-arm calibration ingestion interfaces.
7. Prototype per-vertebra articulated registration with a small internal cohort.
8. Add uncertainty/QC slots to every interface from day one.
9. Wire the GUI to show:
   - segmentations
   - landmarks
   - planes
   - per-vertebra transforms
   - measurement values
   - QC flags
10. Create an error taxonomy and benchmark dashboard.

---

## 19. Guidance for new agents

If you are a new agent joining SpineLab, do this first:

1. Read Sections 2, 5, 7, 8, 12, and 16.
2. Assume the spine is an **articulated rigid-body chain with deformable joints**, not a single deformable object.
3. Preserve measurement definitions. If you change one, version it and document why.
4. Prefer validated baselines over fashionable architectures.
5. Every model output must expose confidence and failure conditions.
6. Never compute a metric that the field of view cannot support.
7. Keep projected/radiographic measurements separate from native-3D ones.
8. Build with provenance and reproducibility from the start.
9. Use the GUI as a learning system, not only a display system.
10. When in doubt, choose the design that a spine surgeon can audit.

---

## 20. Minimal file/data contracts to implement next

### 20.1 `segmentation.json`
Should include:
- patient/study/series IDs
- modality
- model name/version
- label map path
- voxel spacing
- orientation
- QC summary
- per-label confidence if available

### 20.2 `mesh_manifest.json`
Should include:
- source segmentation version
- source segmentation artifact ID
- source volume ID
- extraction algorithm
- label-map path and affine
- smoothing/decimation settings
- point-cloud sampling settings
- raw mesh path
- high-res mesh path
- inference mesh path
- point-cloud path
- source coordinate frame
- coordinate frame
- crop bounds / ROI provenance
- QC summary and component statistics
- checksum

### 20.3 `landmarks.json`
Should include:
- vertebral level
- landmark name
- coordinates
- coordinate frame
- confidence
- model version
- supporting geometry IDs

### 20.4 `pose_graph.json`
Should include:
- vertebral nodes
- parent/adjacency structure
- rigid transforms
- uncertainty
- registration objective summary
- image IDs used
- calibration status

### 20.5 `measurements.json`
Should include:
- metric name
- value
- units
- definition version
- projected vs native3D flag
- confidence interval / uncertainty
- required primitives
- validity flag
- why invalid if invalid
- source artifact IDs

---

## 21. Compute notes

Current available hardware:
- i9-12900K
- RTX 4090 (24 GB VRAM)
- 128 GB DDR5 RAM

This is enough to:
- prototype the full software stack
- run inference comfortably
- train moderate custom models
- train nnU-Net ResEnc-L-scale configurations at least for some tasks, since the official nnU-Net docs target ResEnc-L to ~24 GB VRAM. [R1]

It is not the final compute answer for:
- large multi-cohort retraining
- big ensembles
- broad hyperparameter sweeps
- heavy multi-view registration research at scale

Plan for eventual access to shared GPU servers or cloud/HPC, but do not let that block local progress.

---

## 22. Final project thesis

SpineLab should be built around one core thesis:

> The spine is best modeled as a patient-specific articulated anatomical system whose clinically meaningful motion can be recovered from sparse 2D imaging by combining strong 3D subject anatomy, polyrigid pose estimation, anatomically grounded landmarks, and versioned measurement logic.

That thesis is both technically coherent and clinically relevant.

If executed well, the result is not just another segmentation project. It is a platform for:
- 3D motion quantification
- deformity measurement
- intraoperative guidance
- planning support
- longitudinal outcome analytics

That is worth building.

---

## 23. Source basis used for this document

### Provided project briefs
- `pointcloud_spine_briefing.pdf`
- `vertebral_landmarks_report.pdf`
- `ct_mri_segmentation_briefing.pdf`

### Verified external references
- [R1] nnU-Net residual encoder presets / recommended default: https://github.com/MIC-DKFZ/nnUNet/blob/master/documentation/resenc_presets.md
- [R2] Isensee et al., *nnU-Net Revisited: A Call for Rigorous Validation in 3D Medical Image Segmentation*: https://arxiv.org/abs/2404.09556
- [R3] Wasserthal et al., *TotalSegmentator: Robust Segmentation of 104 Anatomic Structures in CT Images*: https://pmc.ncbi.nlm.nih.gov/articles/PMC10546353/
- [R4] Krishnaswamy et al., *Benchmarking of deep learning methods for generic MRI multi-organ abdominal segmentation*: https://pubmed.ncbi.nlm.nih.gov/41357685/
- [R5] Zhou et al., *MRAnnotator: multi-anatomy and many-sequence MRI segmentation of 44 structures*: https://academic.oup.com/radadv/article/2/1/umae035/7926889
- [R6] D’Antonoli et al., *TotalSegmentator MRI: Robust Sequence-independent Segmentation of Multiple Anatomic Structures in MRI*: https://pubmed.ncbi.nlm.nih.gov/39964271/
- [R7] *Frequency-enhanced Multi-granularity Context Network for Efficient Vertebrae Segmentation (FMC-Net)*: https://arxiv.org/abs/2506.23086
- [R8] Qian et al., *PointNeXt: Revisiting PointNet++ with Improved Training and Scaling Strategies*: https://arxiv.org/abs/2206.04670
- [R9] Pang et al., *Masked Autoencoders for Point Cloud Self-supervised Learning (Point-MAE)*: https://arxiv.org/abs/2203.06604
- [R10] Wang et al., *Point Clouds Meets Physics: Dynamic Acoustic Field Fitting Network for Point Cloud Understanding (DAFNet)*: https://openaccess.thecvf.com/content/CVPR2025/html/Wang_Point_Clouds_Meets_Physics_Dynamic_Acoustic_Field_Fitting_Network_for_CVPR_2025_paper.html
- [R11] Adams & Elhabian, *Point2SSM++: Self-Supervised Learning of Anatomical Shape Models from Point Clouds*: https://arxiv.org/abs/2405.09707
- [R12] Huo et al., *Automatic Vertebral Rotation Angle Measurement of 3D Vertebrae Based on an Improved Transformer Network*: https://pmc.ncbi.nlm.nih.gov/articles/PMC11487434/
- [R13] Hempe et al., *Shape Matters: Detecting Vertebral Fractures Using Differentiable Point-Based Shape Decoding*: https://www.mdpi.com/2078-2489/15/2/120
- [R14] Gopalakrishnan et al., *PolyPose: Deformable 2D/3D Registration via Polyrigid Transformations*: https://pmc.ncbi.nlm.nih.gov/articles/PMC12148084/
- [R15] Garg et al., *EOS imaging: Concept and current applications in spinal disorders*: https://pmc.ncbi.nlm.nih.gov/articles/PMC7452333/
- [R16] Ao et al., *SafeRPlan: Safe deep reinforcement learning for intraoperative planning of pedicle screw placement*: https://www.sciencedirect.com/science/article/pii/S1361841524002706
- [R17] Abel et al., *Deep-learning reconstructed lumbar spine 3D MRI for surgical planning: pedicle screw placement and geometric measurements compared to CT*: https://pubmed.ncbi.nlm.nih.gov/38472429/
- [R18] Massalimova et al., *Feasibility of automatic screw planning via transformer-based shape completion from RGB-D imaging*: https://www.nature.com/articles/s41598-025-21477-6
- [R19] Löffler et al., *A Vertebral Segmentation Dataset with Fracture Grading (VerSe 2019 resource)*: https://pmc.ncbi.nlm.nih.gov/articles/PMC8082364/

---
