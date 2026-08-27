# Stack selection and hybrid handoff

Choose the modelling authority before construction. The best point-cloud
processor, agent interface, visual reviewer, and production CAD kernel need not
be the same application.

## Separate the four roles

1. **Evidence engine** — preserves, aligns, segments, fits, and measures the
   point cloud. Prefer CloudCompare or Open3D for large numerical work.
2. **Interactive workbench** — exposes crops, sections, sketches, overlays, and
   local corrections to a human or agent. This can be Blender, a purpose-built
   browser viewer, BricsCAD, FreeCAD, or another CAD host.
3. **Modelling authority** — owns the editable design-intent feature graph.
   Use a B-rep kernel when STEP/DWG, CNC, or analytic-surface audit is required.
4. **Delivery validator** — independently reopens the declared output and
   checks dimensions, topology, surfaces, and any derived mesh.

Do not let a convenient display mesh silently become the modelling authority.

## Route matrix

| Route | Best use | Authority | Strength | Limitation |
| --- | --- | --- | --- | --- |
| CloudCompare + BricsCAD | Existing Payo-style desktop workflow | DWG/3DSOLID or STEP | Native point-cloud sketching and broad surface commands | Proprietary, GUI-dependent automation |
| Open3D + bundled `$cad` | Open-source analytic reconstruction and manufacturing output | OpenCascade STEP | Deterministic, scriptable B-rep and independent validation | Less interactive point-cloud authoring |
| Blender + CAD Sketcher + local agent bridge | AI-operated visual exploration, simple analytic profiles, scene evidence, and exception handling | Native `.blend` during exploration; STEP must be regenerated elsewhere when required | Strong agent surface, rendering, overlays, Geometry Nodes, reversible review | Display-density pressure, extension-version coupling, no implied STEP authority |
| Tiled browser viewer + replayable OCCT chain | Repeatable product workflow for large clouds | Serialized operation chain plus OCCT STEP | Purpose-built crop/fit UX, streaming, testable regeneration | Requires a maintained application; browser/WASM memory constraints |
| Open3D/SciPy/Trimesh mesh-first | Organic anatomy, scan-following shells, fit coupons, and print-only prototypes | Procedural source plus validated STL | Excellent registration and watertight mesh generation | Not editable analytic CAD; unsuitable as a STEP claim |

For a rigid manufactured part, prefer an analytic B-rep authority. For an
organic print-fit object, a mesh-first route can be honest and effective when
the requested deliverable is STL and physical fit remains separately tested.

## Recommended hybrid architecture

```text
immutable scan
  -> CloudCompare/Open3D alignment and feature-local fits
  -> versioned feature contract
  -> OpenCascade/BricsCAD production B-rep
  -> Blender or browser overlay and agent review
  -> fixed cloud-to-CAD and CAD-to-cloud validation
  -> reopened STEP/DWG and structurally checked derived STL
```

Blender or a browser workbench may propose parameters and topology, but the
production authority consumes an explicit contract and is validated against
the original evidence. Never reverse the handoff by rebuilding production CAD
from a tessellated preview when analytic parameters are available.

## Minimum feature-contract artifact

Store a versioned JSON or equivalent machine-readable record beside derived
artifacts. Keep private source paths out of publishable examples.

```json
{
  "schema_version": "1.0",
  "source": {
    "sha256": "<digest>",
    "format": "ASC XYZ Nx Ny Nz",
    "point_count": 0,
    "units": "mm",
    "units_status": "verified|provisional"
  },
  "alignment": {
    "source_to_cad_4x4": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
    "datum_evidence": ["<datum and confidence>"]
  },
  "components": [
    {
      "id": "main-body",
      "authority": "step",
      "primitive_chain": ["profile", "extrude"],
      "included_features": [],
      "excluded_features": []
    }
  ],
  "parameters": {
    "raw_fit": {},
    "regularized": {},
    "units": "mm"
  },
  "validation": {
    "masks": {},
    "tolerances": {},
    "directions": ["cloud_to_cad", "cad_to_cloud"],
    "required_percentiles": [95, 98]
  }
}
```

The actual contract may add profiles, constraints, component transforms,
surface classes, clearances, and repeated-feature instances. It must retain
raw fitted values alongside regularised design values.

## Browser/OCCT product route

When a purpose-built browser application exists, keep its tiled cloud viewer
and CAD kernel behind explicit interfaces:

- Stream point-cloud tiles with level-of-detail and a fixed memory budget;
  avoid keeping the full cloud and a complex WASM B-rep in one heap.
- Make crop, alignment, section, fit, sketch, and solid operations a replayable
  serialized chain. Editing an earlier parameter must deterministically rebuild
  downstream state.
- Expose domain operations and evidence queries to agents directly when adding
  MCP automation. Page clicks are a fallback, not the durable API.
- Keep fit-time residuals and persistent X-ray overlays available throughout
  construction, then run fixed export-time checks separately.
- Treat advanced guide-rail lofts, patch/stitch continuity, and repeated-feature
  orientation as kernel canaries. A visually plausible browser preview is not
  evidence that the emitted B-rep has the intended topology.
- Round-trip STEP through an independent desktop or OpenCascade reader. A
  same-kernel export/import test is useful but not sufficient as the only gate.
- Preserve autosave and operation-chain recovery so a browser or kernel crash
  does not erase the last accepted modelling state.

## Handoff gates

- Hash and count the immutable source once; carry the identity across tools.
- Record the numerical measurement sample and visual display sample separately.
- Verify units, transform determinant, handedness, and post-handoff bounds.
- Keep cables, connectors, fixtures, anatomy, and other distinct components
  separate until their topology and fit contracts pass.
- Re-run the same masks and directions against the production B-rep, not only
  the workbench preview.
- Reopen the final STEP/DWG independently. A reopened `.blend` proves the
  workbench artifact, not the production CAD handoff.
