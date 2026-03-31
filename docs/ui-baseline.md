# UI Baseline

The frozen reference UI lives in `prototypes/electron-ui/`.

## Preserve

- Windows 11 dark, flat, neutral shell
- One top chrome row with logo, menus, and workspace switching
- Three workspaces:
  - Import
  - Measurement
  - Report
- Left / center / right pane grammar
- Dark scrollbars
- Rounded concentric surfaces with compact spacing
- No gradients

## Improve During Rebuild

- Replace Electron/React runtime with native PySide6
- Move all visual constants into theme tokens
- Make sidebars and panels resizable with invisible handles
- Persist layout state per workspace
- Add Blender-inspired 3D viewport tooling with solid, transparent, wire, and points modes

