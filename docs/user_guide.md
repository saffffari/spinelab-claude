# SpineLab 0.2 User Guide

## Import

- Use `File -> New Case` to start a blank transient session.
- Use `File -> Open Case...` to open a saved `.spine` package.
- Use `File -> Open Legacy Case Folder...` only when you need to migrate an older folder-backed case into the current session model.
- Use `File -> Save Case` or `File -> Save Case As...` to persist the current session as `.spine`.
- `File -> Save Case As...` writes a new case package with a new `case_id`.
- Unsaved sessions live in a transient workspace under `%LOCALAPPDATA%\SpineLab\sessions`.
- If you close a dirty session, SpineLab prompts to `Save`, `Discard`, or `Cancel`.
- SpineLab does not offer crash recovery in `v0.1`; unsaved sessions are purged after abnormal termination.
- Use the blue import control at the top of the `Images` section to browse files or drop source images into the case.
- Drop files directly onto the AP, LAT, or CT viewports to import and assign them in one step.
- Drag assets from the library into a viewport to reassign an existing image set.
- The first imported CT automatically fills the CT viewport if it is empty. The first imported X-rays also auto-fill AP or LAT when the filename or DICOM metadata makes the projection explicit. If projection inference is ambiguous, the asset stays unassigned so you can place it manually.
- Patient Explorer shows saved `.spine` packages from the recent/opened package catalog only.
- Right-click a case in Patient Explorer and choose `Remove from Explorer` to remove it from that catalog without deleting anything from disk.
- Use `File -> Clear Cases` to clear the explorer catalog without deleting any package files from disk.
- Use the comparison selectors in the left action card to define the two modalities used by `Analyze`.
- The Import workspace shows the resolved production segmentation bundle as a read-only status field. Operators do not choose between segmentation models in-app.
- Use `File -> Make DRRs for Testing` to generate temporary bilateral AP/LAT CT projections for the current session. Those images are written into the transient session `drr` folder and assigned as the current standing inputs.
- `Analyze` lives in the left action card beneath the Turbo performance control and runs the local backend pipeline, writing stage-owned artifacts into the transient session `analytics/derived/` tree.
- If no active production bundle is installed, `Analyze` stops with an explicit setup error instead of falling back silently.
- Old cases that previously selected a retired temporary segmentation profile are normalized back onto the production path automatically when they load through the operator workflow.
- Measurement and Report stay pending until `Analyze` completes from Import for the current case session.
- When `Analyze` completes, SpineLab automatically switches to the Measurement tab.
- The Import center toolbar keeps the CT z-stack slice slider above the center viewports instead of inside the CT viewport footer.

## Viewports

- All 2D, orthographic, and 3D review viewports use middle-mouse drag for pan.
- Scroll wheel zooms every viewport by default.
- The CT z-stack viewport uses plain wheel for slice navigation.
- Hold `Ctrl` while scrolling in the CT z-stack viewport to zoom instead of changing slices.
- The header reports the current GPU/CPU render preference for the desktop session.
- The header loading capsule activates during case loads, workspace refreshes, and heavy tab switches.
- If SpineLab detects software OpenGL or cannot confirm hardware OpenGL, Measurement and Report keep the app running but block interactive 3D viewports until the renderer issue is fixed.
- `Analyze` prepares Measurement and Report up front, so opening those tabs after analysis should not trigger their heavy first-build cost.
- Measurement starts with the baseline skeleton visible, keeps the standing overlay hidden until you enable it, and does not auto-lock any vertebra as the starting primary selection.
- Before `Analyze` runs, Measurement and Report keep their center area black instead of preloading models or report values.
- If you open Measurement before `Analyze`, each viewport shows a red `No Analysis Performed` warning until the analysis finishes.

## Measurement

- Select vertebrae from the list, the viewport, or the orthographic views.
- `PELVIS` is now a first-class selectable structure in the Measurement scene.
- `Ctrl`-select removes a vertebra from the current selection.
- Use `Set Reference Frame` in the left action card to make the current active selection the motion basis.
- The right inspector shows the current `Global Axis` as `<PRIMARY> local Z` whenever a primary anchor is active.
- The primary vertebra renders green in the 3D and orthographic views, while additional selected vertebrae stay orange and add primary-relative motion columns in the right inspector.
- The live measurement 3D controls use four mesh render modes:
  - `Points`
  - `Wireframe`
  - `Translucent`
  - `Solid`
- Use the top Measurement toolbar to change render mode and choose `Low`, `Med`, or `High` detail.
- Use the left action card to toggle `Supine` and `Standing` visibility. Shown poses are blue and hidden poses are orange.
- `Solid` keeps shaded surfaces without the wireframe edge overlay.
- The right inspector uses manifest-backed metric records when available and packs value, unit, stage, confidence, provenance, and primary-relative motion into compact columns.
- `Save Measurements` and `Export Model` now live in the same left action card so the major workflow buttons stay in one place.
- `Save Measurements` prompts for a destination folder and exports the selected measurements to PDF.
- `Export Model` prompts for a destination folder and writes a structured measurement export bundle there.
- The export bundle includes selected baseline meshes, copied standing scene assets, copied standing AP/LAT inputs when present, a measurements PDF/JSON pair, and copied stage artifacts.
- The bundle also includes bilateral standing AP/LAT scaffold projections generated from the standing mesh scene. These are current mesh-projection surrogates, not final NanoDRR volume-integral exports.

## Report

- Use the left report navigation to jump between overview, alignment, regional, vertebral, and export sections.
- The hero viewport camera buttons switch between 3D, front, side, and top views.
- KPI cards and vertebral detail rows now prefer manifest-backed target and measurement records over placeholder strings.
- Export actions produce PDF and CSV outputs from the current report dataset.
