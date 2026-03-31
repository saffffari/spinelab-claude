# SpineLab `.spine` Format

## Overview

SpineLab `v0.1` uses a single `.spine` file as the normal durable case format.

- A `.spine` file is the case.
- The file is a standard ZIP archive written with ZIP64 support.
- The unpacked export layout matches the internal archive layout exactly.
- The archive is authoritative. It is not a sidecar manifest or a pointer to an external case folder.

SpineLab remains path-based internally. When a case is opened, the archive is extracted into a transient session workspace under `%LOCALAPPDATA%\SpineLab\sessions\...`. The application then works against those real files until the user chooses `Save Case` or `Save Case As`.

## Security And Session Rules

- Unsaved work lives only in the transient session workspace.
- SpineLab does not provide crash recovery in `v0.1`.
- If the application terminates unexpectedly, unsaved PHI is not restored.
- Orphaned transient session directories are purged on next startup.
- Runtime-only metadata, temp files, caches, and logs are not written into the `.spine` package.

## Required Package Layout

Every `.spine` archive contains these root entries:

```text
<CASE_ID>.spine
  manifest.json
  dicom/
    ct/
    mri/
    xray/
  ct/
  mri/
  xray/
  drr/
  3d/
    supine/
    standing/
  analytics/
```

Rules:

- All directories above are written explicitly, even when empty.
- Package and folder naming uses `case_id`, never patient name.
- Paths stored in the package manifest use forward slashes and are always relative.
- Original DICOM files are preserved byte-for-byte under `dicom/...`.

## Manifest Contract

The package root `manifest.json` is the authoritative saved-case index.

Current top-level fields:

- `schema_version`
- `case_id`
- `patient_id`
- `patient_name`
- `created_utc`
- `updated_utc`
- `assets`
- `scene`
- `dicom_index`
- `patient_metadata`
- `analysis_state`

### `assets`

Every packaged payload file is represented in `assets`, excluding directory entries and the root `manifest.json` itself.

Each asset records at least:

- `id`
- `type`
- `path`
- `format`
- `sha256`
- `size_bytes`

Optional fields are used when available, including:

- `subtype`
- `role`
- `pose`
- `structure`
- `source_asset_id`
- `created_utc`
- `dicom_refs`
- `label`
- `status`

### `scene`

The saved scene stores asset-ID-based references rather than raw filenames. Current fields include:

- `primary_ct_id`
- `role_bindings`
- `comparison_modalities`
- `active_pose`
- `visible_asset_ids`
- `transform_artifact_ids`

### `dicom_index`

`dicom_index` stores extracted organizational and geometry metadata so SpineLab can validate and rebuild the runtime scene without reparsing every DICOM file on startup.

Current entries preserve:

- source identity such as `patient_id`, study UID, series UID, and SOP UID
- modality and descriptive tags when present
- scanner and acquisition metadata when present
- image geometry and spacing fields when present
- file counts and per-instance references back to packaged DICOM asset paths

### `analysis_state`

`analysis_state` is a repo-specific convenience mirror of the runtime `CaseManifest`, rewritten with package-relative paths. It exists so the current GUI and pipeline code can reopen a saved case without replacing the runtime model wholesale.

This field is intentionally additive. The durable saved-case contract remains the package `manifest.json`.

## Open, Save, And Export Behavior

### Open Case

`File -> Open Case...`

- validates the `.spine` archive
- extracts it into a transient session workspace
- loads the runtime manifest and DICOM catalog into session runtime metadata
- makes the session available to Import, Analyze, Measurement, and Report

### Open Legacy Case Folder

`File -> Open Legacy Case Folder...`

- loads a folder-backed legacy case into a transient session
- keeps the legacy folder out of the normal Patient Explorer catalog
- requires `Save Case As` if the user wants a durable `.spine` package afterward

### Save Case

`File -> Save Case`

- overwrites the current `.spine` path when the session already came from a saved package
- writes through a temporary file and then atomically replaces the destination
- preserves stable asset and artifact identifiers where possible

### Save Case As

`File -> Save Case As...`

- assigns a new `case_id`
- writes a new `.spine` file
- preserves patient metadata and provenance links

### Export Package Folder

`File -> Export Package Folder...`

- writes an unpacked folder with the exact same layout as the `.spine` archive
- preserves empty logical directories explicitly

### Export Assets

`File -> Export Assets...`

Current user-facing asset groups include:

- original DICOM
- standardized CT
- DRRs
- meshes
- analytics and reports

## Legacy Compatibility

SpineLab can still open legacy folder-backed cases as transient migration inputs.

Rules:

- legacy case folders are not the preferred saved format
- opening a legacy case creates a transient session only
- durable persistence from that point forward requires `Save Case As`

## Versioning

- Current schema version: `0.1`
- Loader validation rejects unsupported schema versions with a clear error
- Migration dispatch is present from day one so future versions can be added without replacing the archive format
