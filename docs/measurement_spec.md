# SpineLab Measurement Specification

This is the operational source for metric definitions, validity gating, and required primitives.

Keep this document in sync with [docs/spinelab_manifesto.md](/D:/claude/spinelab/docs/spinelab_manifesto.md).

## Measurement Principles

1. Measurement definitions are versioned.
2. Never silently redefine a metric.
3. Keep projected radiograph-equivalent metrics separate from native 3D metrics.
4. All measurements live in an explicit global coordinate context.
5. Never compute a metric the field of view cannot support.
6. Every reported value carries provenance, uncertainty, and validity status.

## Imported Measurement Dependency Package

The repo now carries an imported measurement-oriented ontology package as a single canonical file:

- [docs/ontology/spinelab_vertebral_labeling_ontology.yaml](/D:/claude/spinelab/docs/ontology/spinelab_vertebral_labeling_ontology.yaml)

That file is frozen and must not be edited without explicit user approval.

Use it as the imported source for:

- landmark-code naming
- measurement dependency review
- field-of-view support examples
- future module breakdown for geometry and measurement implementation

Do not silently rewrite the runtime ontology or the current metric ids to mirror imported wording. Reconciliation requires explicit approval and deliberate versioning.

## Metric Modes

For each clinically recognized metric, store both when possible:

- Projected or radiograph-equivalent
  - Computed from the posed 3D model after projection into the clinically relevant plane.
  - Intended to match standard radiographic definitions.
- Native 3D
  - Computed directly on posed 3D anatomy.
  - Intended for research and richer geometric interpretation.

## Core Metrics to Support

### Local or disc level

- anterior disc height
- middle disc height
- posterior disc height
- disc midpoint height
- disc space angle
- spondylolisthesis or retrolisthesis
- segmental lordosis or kyphosis

### Regional sagittal

- lumbar lordosis
- thoracic kyphosis
- thoracolumbar junction kyphosis
- apex of lordosis

### Spinopelvic

- pelvic incidence
- pelvic tilt
- sacral slope

### Global sagittal or coronal

- sagittal vertical axis
- coronal balance or C7-CSVL distance
- scoliosis Cobb angles for PT, MT, and TL/L curves
- vertebral rotation descriptors when available

## Current House Conventions

Until versioned changes are explicitly approved, use:

- Lumbar lordosis: L1 superior endplate to S1 superior endplate
- Thoracic kyphosis: T4 superior endplate to T12 inferior endplate
- Thoracolumbar junction kyphosis: T10 superior endplate to L2 inferior endplate

If a nonstandard convention is adopted later, version it. Do not silently switch.

## Required Primitives by Metric

### Disc height

Needed:

- inferior endplate of cranial vertebra
- superior endplate of caudal vertebra
- disc centerline or disc midpoint

Store anterior, middle, and posterior heights, not just one value.

### Listhesis

Needed:

- posterior wall or posterior body corners of adjacent levels

Define translation in a segment-specific coordinate frame, not only global AP space.

### Disc space angle

Needed:

- inferior endplate plane of upper vertebra
- superior endplate plane of lower vertebra

### Pelvic incidence, pelvic tilt, sacral slope

Needed:

- S1 superior endplate plane and midpoint
- bilateral femoral head centers or hip axis
- explicit vertical and horizontal references where required

### Lumbar lordosis

Needed:

- superior endplate of L1
- superior endplate of S1

### Segmental lordosis

Needed:

- the specific bounding endplates for the chosen segment

### Apex of lordosis

Needed:

- a curve-based, versioned definition

Do not use an undocumented heuristic.

### Thoracic kyphosis

Needed:

- T4 superior endplate
- T12 inferior endplate

### SVA

Needed:

- C7 center
- vertical plumb line reference
- posterior-superior S1 corner

### Coronal balance

Needed:

- C7 center
- sacral midline or CSVL

### Scoliosis Cobb angles

Needed:

- endplate planes across the curve region
- end-vertebra selection logic
- apical vertebra identification logic

## Validity Gating

If imaging is incomplete:

- You may compute:
  - disc height
  - listhesis
  - segmental lordosis
- You may not compute:
  - SVA
  - pelvic parameters
  - full scoliosis metrics

Do not report unavailable metrics as numeric zero or low-confidence placeholders. Mark them invalid and explain why.

## Output Requirements

Every stored measurement should include:

- metric name
- value
- units
- definition version
- projected versus native-3D mode
- uncertainty or confidence interval
- required primitives used
- validity flag
- invalidity reason when invalid
- source artifact IDs and transform context

## QC Rules

- Do not let UI convenience override clinical correctness.
- Distinguish between "can be computed" and "should be trusted."
- Favor fail-closed behavior over smooth-looking wrong answers.
- Surface unsupported field of view, low-confidence primitives, and registration uncertainty directly in the measurement result.
