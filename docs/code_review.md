# Code Review Checklist

## Findings First

- Prefer bugs, regressions, and risky assumptions over style commentary.
- Check whether shared workspaces, services, or theme tokens were missed.

## Theme Discipline

- No raw hex colors outside theme files
- No font weights above regular
- No stray spacing or radius literals where tokens already exist
- No visible splitter-handle chrome

## Workspace Consistency

- Import, Measurement, and Report still share the same shell grammar
- Sidebars collapse and restore widths correctly
- Splitter persistence still restores cleanly
- Analyze still refreshes the other tabs from the updated manifest after pipeline work completes
- Visual signoff ran in the real `MainWindow` shell; standalone workspace windows were treated as debug-only scaffolds

## Viewer Risks

- 3D modes still render correctly in solid, transparent, wire, and points
- Selection still focuses the chosen model centroid
- No transform-editing affordances are exposed
- Volumetric rendering preserves the same viewport shell grammar and navigation contract
- Viewport navigation remains consistent:
  - middle-mouse drag pans every 3D, orthographic, and 2D image viewport
  - wheel zooms by default
  - import CT z-stack keeps plain wheel slice navigation and `Ctrl` + wheel zoom

## Backend Risks

- The main desktop environment stays free of research-sidecar dependencies
- `envs/` manifests exist for each external backend tool declared by the adapters
- Pipeline runs persist device, environment, version, inputs, and outputs
- Re-running analysis clears and regenerates stage-owned artifacts, metrics, findings, and normalized volumes cleanly
- CPU fallback remains available when CUDA is unavailable
- External test-image manifests materialize into safe editable case ids before local analysis writes derived outputs

## Verification

- Theme checker runs clean
- Targeted tests ran
- Broader lint, type, and test checks ran when shared code changed
- Shell-level UI checks exercised the production application bootstrap rather than a generic `QApplication`
