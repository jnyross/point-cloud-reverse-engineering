# Stack selection and hybrid handoff

Choose the modelling authority before construction. The best evidence engine,
agent interface, visual reviewer, modelling authority, and delivery validator
need not be the same application.

When this file is reached from the read-only dispatcher, compare and recommend
only: do not create files, configure tools, or mutate geometry. When reached by
an explicitly scoped combine/integrate/orchestrate request, freeze the decision
and validated handoff contract first, then execute only through the selected
authority playbooks.

## Separate the roles

1. **Evidence engine** preserves, aligns, segments, fits, and measures the fixed
   point cloud. Prefer CloudCompare or Open3D for large numerical work.
2. **Interactive workbench** exposes crops, sections, sketches, overlays, and
   local corrections to a human or agent.
3. **Modelling authority** owns the editable/replayable feature graph or
   procedural source. It determines what editability claims are valid.
4. **Delivery validator** reopens the declared output through the strongest
   available validation tier and checks evidence-local as well as global facts.

Do not let a display tile, display sample, evaluated object, or convenient mesh
silently become measurement evidence or modelling authority.

## Decide from disqualifiers first

1. Identify the required primary authority: native Fusion F3D, editable
   STEP/DWG, native BLEND, replayable OCCT chain, or procedural mesh/STL-only.
2. Classify critical geometry as manufactured analytic, section-controlled,
   freeform manufactured skin, organic scan-following, or mixed by component.
3. Reject a route that cannot represent the required authority, topology,
   component split, unit calibration, uncertainty, or independent validation.
4. Among viable routes, compare evidence capacity, local edit/recovery loop,
   deterministic replay, agent surface, runtime availability, memory risk, and
   validation independence.
5. Record the selected authority, reasons, rejected alternatives, required
   deliverables, host/runtime versions, and unresolved canaries before acting.

Consult the repository's [recorded compatibility evidence](../../../compatibility.json)
and, before an execution route, run the read-only
[compatibility preflight](../../../scripts/compatibility_preflight.py). A detected
binary, extension manifest, or package is not proof that the integrated route
works; `unknown`, probe-only, and concrete incompatibility remain distinct.

## Route matrix

| Route | Best use | Authority | Main limitation |
| --- | --- | --- | --- |
| Open3D/CloudCompare + Autodesk Fusion | Agent-operated rigid manufactured products, native parametric editability, multi-body assemblies, and visual-fidelity review | Native F3D plus derived STEP | Proprietary desktop GUI/API; weak fit for headless CI or organic geometry |
| CrealityScan/CloudCompare + BricsCAD | Existing desktop workflow, local point-cloud sketching, guide-rail lofts and stitched surfaces | DWG/3DSOLID or exported STEP | Proprietary and GUI-dependent |
| Open3D/CloudCompare + bundled `$cad` | Scripted manufactured reconstruction and manufacturing output | OpenCascade STEP | Less interactive point-cloud authoring |
| Blender + CAD Sketcher + local bridge | AI-operated overlays, scene evidence, simple constrained profiles and exception handling | Native BLEND during exploration; regenerate STEP elsewhere if required | Display-density and extension-version pressure; no implied B-rep authority |
| Tiled browser viewer + replayable OCCT | Purpose-built streaming crop/fit UX and deterministic product workflow | Serialized chain plus OCCT B-rep | Application maintenance and browser/WASM resource constraints |
| Open3D/SciPy/Trimesh mesh-first | Organic anatomy, scan-following shells, fit coupons and print-only prototypes | Procedural source plus validated STL | Not editable analytic CAD and unsuitable as a STEP claim |

For a rigid manufactured part, prefer analytic B-rep authority. For an organic
print-fit object, mesh-first can be more honest when STL is the required output.
For mixed parts, preserve separate components and assign authority per component;
do not force a cable or organic contact shell into the enclosure's primitive
chain.

## Preferred hybrid loop

```text
immutable scan
  -> calibrated CloudCompare/Open3D evidence and feature-local fits
  -> schema-valid feature contract
  -> selected authority builds/replays one bounded feature
  -> Blender/browser/desktop defining-section review
  -> same fixed local + global evidence and uncertainty gates
  -> accept checkpoint or revert one feature
  -> strongest available reopen/interchange validation
```

A workbench may propose topology and parameters, but the authority consumes an
explicit contract and is revalidated against the original fixed evidence. Never
rebuild production analytic CAD from a tessellated preview when analytic
parameters and sections are available.

## Machine-readable handoff

Use [the feature-contract schema](../assets/feature-contract.schema.json), start
from [the canonical valid example](../assets/contracts/feature-contract.valid.json),
and run [the contract validator](../scripts/validate_feature_contract.py) before
the first authority mutation and after each accepted parameter/topology change.
Use [the evidence CLI](../scripts/point_cloud_evidence.py) for deterministic
source fingerprint, unit/bounds preflight, and bounded evidence summaries when
the source format is supported.

Contract v1 carries one independently accepted component. Use separate
contracts for separate bodies or assembly components, then aggregate their
statuses without weakening any component gate. Each contract must retain at
least:

- source and derivative checksums/counts, verified or provisional units, and
  independent calibration evidence;
- explicit source-to-authority transform direction, matrix layout, frames,
  handedness, determinant, and tested inverse;
- component authority, primitive/mesh intent, dependencies, included and
  excluded features, raw fits, regularised parameters, and repeated instances;
- fixed masks, directions, semantic surface/normal/coverage/section metrics,
  tolerance, uncertainty budget, exclusions, and resource limits;
- required deliverables, authority-specific completion gates, validation tier,
  tool/kernel versions, and unverified physical claims.

Keep private source paths and user data out of publishable examples. A valid
schema proves contract shape, not correctness of its geometric evidence.

## Execute the selected authority

- Desktop CloudCompare/BricsCAD: follow [operate.md](operate.md) after the shared
  preconstruction gates.
- Autodesk Fusion: follow
  [autodesk-fusion.md](authorities/autodesk-fusion.md).
- Linux analytic B-rep: follow [linux-open-source.md](linux-open-source.md).
- Blender/CAD Sketcher: follow
  [blender-ai-workbench.md](authorities/blender-ai-workbench.md).
- Browser/replayable OCCT: follow
  [browser-occt-workbench.md](authorities/browser-occt-workbench.md).
- Organic procedural mesh/STL: follow
  [organic-mesh-first.md](authorities/organic-mesh-first.md).

All routes apply the
[shared evidence and validation contract](shared/evidence-and-validation.md).
Selecting or combining tools never relaxes unit calibration, topology, local
fit, uncertainty, replay/reopen, or authority-specific completion gates.

## Read-only decision output

Return the fixed requirements, disqualified routes and reasons, selected route
or unresolved tie, role allocation, authority, deliverables, mandatory canaries,
compatibility risks, evidence gates, and the smallest scoped next action. If two
routes remain viable because a critical fact is unknown, ask for that fact rather
than selecting from convenience.
