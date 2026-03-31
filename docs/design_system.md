# SpineLab Design System

## Palette

- `green-500`: `#53BC3A`
- `blue-500`: `#448FD4`
- `red-500`: `#FC443F`
- `orange-500`: `#FF7D34`
- `yellow-500`: `#F2BD37`
- `neutral-100`: `#BDBDBD`
- `neutral-500`: `#404040`
- `neutral-700`: `#1B1B1B`
- `neutral-800`: `#151515`
- `neutral-900`: `#101010`

## Semantics

- Orange is the primary selection and focus color.
- Green is for stable, ready, and successful states.
- Yellow is mild warning.
- Orange is processing and warning.
- Red is critical and destructive.
- Soft state fills use 20% opacity.
- Neutrals define shell, panel, text, scrollbar, and viewport chrome.

## Typography

- Family: `Segoe UI Variable`
- Display roles prefer `Segoe UI Variable Display`
- Body roles prefer `Segoe UI Variable Text`
- Fallback chain: `Segoe UI Variable`, `Segoe UI`, `system-ui`, `sans-serif`
- Allowed weights only:
  - `300` light
  - `350` semilight
  - `400` regular
  - `500` semibold for major action buttons only

## Type Roles

- `workspace-title`: `20/26`, weight `350`
- `header-brand`: `13/18`, weight `500`
- `panel-title`: `15/20`, weight `350`
- `section-label`: `12/16`, weight `350`
- `body`: `13/18`, weight `400`
- `body-emphasis`: `13/18`, weight `350`
- `major-button`: `13/18`, weight `500`
- `meta`: `12/16`, weight `400`
- `micro`: `11/14`, weight `400`
- `metric-large`: `28/32`, weight `300`

## Geometry

- Base unit is `8px`
- Panel content padding is `8px` and should come from the shared geometry token
- All rectangles are rounded
- Nested rectangles inset by `8px` on every side
- Child radius = parent radius - `8px`, clamped to a minimum rounded value
- Current shared radius ladder:
  - panel shell: `20px`
  - first inset child: `12px`
  - nested inset child: `10px`
- Capsule controls use radius = half of control height
- Text padding stays compact and comfortable, not airy
- UI chrome is fill-only: no border strokes, outline strokes, divider lines, or panel/window edge lines

## Hierarchy Checks

- Any UI change that adds or re-parents a visible block must preserve concentricity with the adjacent parent block.
- Do not reuse the same radius for two layers when one layer is visibly inset inside the other.
- Viewport wrappers, center toolbars, nested cards, and inspector blocks must use the next smaller radius token for their depth.
- Review the live GUI after layout changes to confirm radii remain concentric across:
  - sidebars and section surfaces
  - nested inspector/action/summary cards
  - viewport wrappers and viewport surfaces
  - center toolbars and grouped controls

## Text Hierarchy

- Text brightness follows block depth.
- Top-level panel titles may use the brightest neutral text.
- First inset blocks step down to the secondary neutral text.
- Deeper nested cards and info grids step down again to muted or secondary text depending on emphasis.
- Semantic colors such as orange, blue, green, yellow, and red may override the neutral ladder only for clear state meaning.
- Nested values must never become brighter than the containing block unless a semantic state color is intentional.

## Layout

- Sidebars and major panels are resizable
- Resize handles are behavioral only and visually invisible
- Left and right sidebars are collapsible
- Collapse state restores the last expanded width
- Sidebar width and collapse state persist across all workspace tabs

## Viewport Interaction

- All review viewports share one navigation convention.
- 3D views, orthographic views, and 2D image views use middle-mouse drag for panning.
- Scroll wheel zooms by default in every viewport.
- The import CT z-stack viewport is the only exception:
  - plain wheel scroll changes slices in the stack
  - `Ctrl` + wheel zooms the image
- Any future viewport or viewer refactor must preserve this convention.

## Volumetric Viewports

- The volumetric viewer implementation exists in the repo but is currently disabled in the live measurement tab.
- Volumetric review lives inside the same fill-only viewport shell used by the other viewers.
- Overlay controls stay inside the viewport and use the same rounded chip/button language as the mesh and image viewers.
- The first volumetric viewer supports three modes:
  - `Slice`
  - `Volume`
  - `Isosurface`
- Preset buttons remain visible inside the viewport overlay so users can switch between `Bone` and `Soft` transfer-function windows without leaving the canvas.
- Volumetric rendering is additive; it does not replace the raw CT z-stack review viewport.
