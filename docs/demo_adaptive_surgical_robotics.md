# Adaptive Surgical Robotics — Demo & Presentation Script

## The Pitch (30 seconds)

Every surgical robot on the market registers to the patient's anatomy once at the start of the case, then executes blindly. The spine moves during surgery. They don't know.

SpineLab builds a complete, sub-voxel, per-bone point cloud of every vertebra before surgery starts. That prior converts an impossible real-time perception problem — reconstructing anatomy from a bloody, occluded surgical field — into a tractable one: registering a partial surface view against a known model.

That's the foundation for a robot that continuously sees, continuously replans, and refuses to execute any motion that violates an anatomical safety boundary.

---

## Demo Flow (Live in SpineLab GUI)

### Beat 1: "We already know what every bone looks like" (60s)

- Load a real patient case
- Run the pipeline: CT → segmentation → point clouds
- Show the per-vertebra point clouds in the 3D viewport — each bone individually colored, floating in physical space
- Rotate, zoom. These are sub-voxel smooth. Not blocky. Not aliased.
- **Key line:** *"This is 8,192 points per bone, sub-voxel precision, with surface normals. The robot knows the shape of every vertebra before the patient enters the OR."*

### Beat 2: "The safety field" (60s)

- Toggle on the **spinal canal** segmentation as a transparent red surface
- Show **signed distance coloring**: each point on the vertebral surface colored by its distance to the nearest canal wall
  - Green → far (>8mm)
  - Yellow → caution zone (4–8mm)
  - Red → critical (<4mm)
- **Key line:** *"The robot doesn't just know where bone is. It knows where the spinal cord is. Every point carries a safety margin."*

### Beat 3: "Planned trajectory" (60s)

- Show a pedicle screw trajectory as a cylinder/line from entry point through the pedicle
- Display: entry point on bone surface, approach angle, depth, minimum distance to canal along the path
- The trajectory is green — fully safe
- **Key line:** *"This is a standard pre-operative plan. Every surgical robot on the market stops here."*

### Beat 4: "The spine moves" (60s — this is the moment)

- **Simulate intraoperative shift**: translate L4 laterally by 3mm, rotate 2°
  - (In the GUI: apply a small rigid transform to L4's point cloud in real-time)
- The planned trajectory now passes closer to the canal — turns yellow, then red
- The safety field updates instantly
- A new trajectory is computed automatically — green again, adjusted angle
- Side-by-side: old plan (red, unsafe) vs. adapted plan (green, safe)
- **Key line:** *"The spine shifted 3 millimeters. Every existing robot would have drilled the original path. Ours refused — and found a safe one."*

### Beat 5: "What makes this possible" (30s)

- Zoom into the partial-view overlay:
  - Show only the posterior 30% of L4's surface (what a camera would actually see through a surgical corridor)
  - Show ICP snapping that partial view onto the full pre-op point cloud
  - The full model fills in everything the camera can't see
- **Key line:** *"We don't need to reconstruct the anatomy intraoperatively. We already have it. The sensor just needs to find it."*

---

## Slide Deck (2–3 slides, supporting the demo)

### Slide 1: "The Problem with Surgical Robots"

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│   Every surgical robot today:                           │
│                                                         │
│   1. Pre-op CT scan                                     │
│   2. Register once at start of case                     │
│   3. Execute plan blindly                               │
│                                                         │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐       │
│   │ Pre-op   │ ──▶ │ Register │ ──▶ │ Execute  │       │
│   │ Plan     │     │ Once     │     │ Blindly  │       │
│   └──────────┘     └──────────┘     └──────────┘       │
│                                                         │
│   The spine moves during surgery.                       │
│   The robot doesn't know.                               │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

Talking point: Mazor, ExcelsiusGPS, ROSA — all the same architecture. $200K+ systems that are sophisticated positioning arms, not intelligent agents.

### Slide 2: "The SpineLab Architecture"

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│   PRE-OP                        INTRAOPERATIVE          │
│                                                         │
│   CT ──▶ nnU-Net ──▶ Point      Stereo camera           │
│          Segmentation  Clouds   ──▶ Partial surface     │
│                        ↓              ↓                 │
│                    Per-bone       ICP register           │
│                    models ──────▶ against known ──┐     │
│                        ↓          geometry        │     │
│                    Canal surface                   │     │
│                    (safety zone)                   │     │
│                        ↓                          ↓     │
│                    ┌─────────────────────────────┐      │
│                    │  CONTINUOUS PLANNING LOOP    │      │
│                    │                             │      │
│                    │  Current bone poses         │      │
│                    │  + Safety distance field    │      │
│                    │  + Motion constraints       │      │
│                    │  ──▶ Updated trajectory     │      │
│                    │  ──▶ Execute IF safe        │      │
│                    │  ──▶ REFUSE if not          │      │
│                    └─────────────────────────────┘      │
│                                                         │
│   Key: pre-op point cloud is a STRONG PRIOR             │
│   Intraop sensor does REGISTRATION, not RECONSTRUCTION  │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

Talking point: The pre-op geometry pipeline is built and running. The perception problem changes from "build a model of unknown anatomy" to "find known anatomy in a partial view." That's the architectural insight.

### Slide 3: "What Exists Today vs. What We're Building"

| | Current Robots | SpineLab Adaptive |
|---|---|---|
| Pre-op geometry | CT → manual/semi-auto plan | CT → automatic per-bone point cloud |
| Registration | Once, at case start | Continuous, per-frame |
| Anatomy model | Static snapshot | Live-updated poses |
| Safety enforcement | Surgeon vigilance | Computed signed distance field |
| Response to shift | None (execute original plan) | Refuse unsafe motion, replan |
| Perception model | None after registration | Prior-guided partial-view registration |

---

## What Needs to Exist in the GUI for the Demo

### Must-have (build before demo):

1. **Safety distance coloring**: Color each vertex/point by signed distance to nearest canal surface point. Green/yellow/red gradient. This is the visual centerpiece.

2. **Trajectory visualization**: Render a cylinder or line through a pedicle with entry/exit points. Display minimum canal distance along the path as a floating label.

3. **Simulated shift**: Button or slider that applies a small rigid transform (translation + rotation) to a selected vertebra's point cloud. The trajectory and safety coloring update in real-time.

4. **Adapted trajectory**: After shift, show the replanned trajectory (new entry angle, same target) alongside the original. Original in red, adapted in green.

### Nice-to-have (if time permits):

5. **Partial view overlay**: Show a frustum-shaped subset of a vertebra's points (simulating a camera's view through a surgical corridor), then show ICP alignment snapping it to the full model.

6. **Safety zone toggle**: Click to show/hide the canal surface as a transparent red volume.

7. **Continuous animation**: Slowly drift L4 over 5 seconds while the trajectory smoothly adapts — makes the "continuous replanning" concept visceral.

---

## Implementation Notes

### Safety distance coloring

```python
# For each vertebra point cloud:
# 1. Load canal point cloud (already segmented)
# 2. Build KDTree on canal points
# 3. Query nearest distance for each vertebra surface point
# 4. Map to color: green (>8mm) → yellow (4-8mm) → red (<4mm)

from scipy.spatial import cKDTree

canal_tree = cKDTree(canal_points)
distances, _ = canal_tree.query(vertebra_points)
# distances is now per-point signed distance to canal
```

### Trajectory planning (simplified for demo)

```python
# Pedicle screw trajectory:
# - Entry point: centroid of posterior pedicle surface
# - Direction: medial-anterior from entry, ~10-15° convergence
# - Depth: ~40-50mm typical
# - Safety: minimum distance from trajectory cylinder to canal surface

# For the shift simulation:
# - Apply rigid transform to vertebra point cloud
# - Recompute entry point on transformed surface
# - Recompute trajectory with same convergence target
# - Recolor by new safety distances
```

### PyVista rendering

The existing SpineLab viewer uses PyVista with PySide6 Qt integration. All of the above can be rendered with:
- `plotter.add_points()` with scalar coloring for safety distance
- `plotter.add_mesh(pv.Cylinder(...))` for trajectory
- `plotter.add_mesh(canal_surface, opacity=0.3, color='red')` for canal
- Slider widget for shift simulation

---

## Architecture Constraint: Local-Only Processing

Everything runs on the machine in the room. This is non-negotiable for three reasons:

1. **HIPAA** — Patient CT data never leaves the device. No PHI traverses a network. No cloud vendor BAA required. The compliance story is: "the data doesn't leave."

2. **Latency** — An intraoperative perception loop at 10+ Hz cannot tolerate a 200ms cloud round trip. Local GPU inference is sub-10ms. This isn't a preference, it's a physics constraint for the robotics use case.

3. **Reliability** — A surgical robot cannot depend on an internet connection. Local processing means the system works in an OR with no network at all.

For the demo, this is a feature: load a DICOM, click analyze, watch the point clouds appear. No spinners waiting on a server. No "connecting to cloud..." dialog. Just computation happening on the hardware in front of the audience.

**Hardware target:** Consumer/prosumer GPU (RTX 4090 or equivalent). nnU-Net ResEnc M inference + point cloud extraction + safety field computation all fit in 24GB VRAM. The same hardware class that will eventually run the intraop perception loop.

---

## Narrative Arc

The demo tells one story in five beats:

1. **Competence** — we can extract beautiful per-bone geometry from any CT scan
2. **Awareness** — we know where the danger zones are (canal, nerve roots)
3. **Planning** — we can compute safe surgical trajectories through that geometry
4. **The problem** — the anatomy moves, and every current system ignores that
5. **The solution** — continuous perception against a known prior, with hard safety guarantees

Beat 4 is the turn. Everything before it is impressive but incremental. Beat 4 is the moment the audience realizes this is a fundamentally different thing.

---

*Last updated: 2026-04-01*
