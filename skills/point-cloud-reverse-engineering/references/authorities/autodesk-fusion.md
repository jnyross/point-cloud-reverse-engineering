# Autodesk Fusion native authority route

Use this route when the user explicitly requests Autodesk Fusion or a native
`.f3d` deliverable, and when the part is principally manufactured analytic
geometry or a multi-body product whose editable feature tree, components,
appearances, and visual review matter. Fusion is often the best authority for
an agent-operated desktop reconstruction when sketches, extrusions, revolves,
sweeps, lofts, fillets, patterns, and named user parameters can express the
feature contract directly.

Prefer another route for headless or Linux-only work, unattended deterministic
CI, organic scan-following geometry, or a job that needs only an open STEP and
has no native-Fusion requirement.

Apply the [shared evidence and validation contract](../shared/evidence-and-validation.md)
before construction. Fusion owns the native model, not the measurement cloud:
use CloudCompare, Open3D, or a bounded numerical pipeline for full-density
alignment, fitting, masks, and distance evidence.

## Availability and authority gate

1. Inspect the repository's [compatibility evidence](../../../../compatibility.json)
   and run the read-only
   [compatibility preflight](../../../../scripts/compatibility_preflight.py).
   Treat Fusion release, licence state, scripting/API behavior, computer-control
   access, and host unlock state as live canaries rather than assumptions.
2. Do not install Fusion, alter security settings, or grant broad filesystem
   access without explicit approval. If the application cannot be controlled,
   stop at a precise manual handoff.
3. Declare `fusion_f3d` as the primary authority when native editability is the
   deliverable. Declare STEP and each STL as derived artifacts with their own
   gates; an exported STEP does not prove that the `.f3d` is editable.
4. Prove a bounded native canary before the real build: create a fresh document,
   make one parameterized analytic feature and cut, save, reopen, inspect the
   feature/body inventory, and remove only the canary document.

## Clean-room and artifact split

When the user requires a from-scratch reconstruction, freeze an allowed-input
manifest before opening the production document. Hash the untouched scan and
name any allowed calibrated specifications or images. State that prior CAD,
meshes derived from prior CAD, and old parameter files are forbidden, then
create a new Fusion document without Insert, Derive, or copy/paste from an old
design.

Keep these identities separate:

- untouched source scan;
- aligned measurement evidence and fixed masks;
- optional display sample;
- raw fitted values and regularised modelling parameters;
- Fusion build source plus any approved appearance assets;
- native `.f3d` authority;
- derived STEP, one STL per accepted body, renders, and validation reports.

Photographs may resolve feature presence, order, topology, continuity, and
appearance. They are not dimensional evidence unless independently calibrated.
Do not let a familiar product identity import dimensions from an earlier model.

## Native construction

1. Start from a fresh document with explicit units, origin, component frame,
   and source-to-Fusion transform. Recheck held-out datums and bounds after the
   handoff.
2. Put raw fits and regularised values in a versioned parameter artifact. Expose
   dimensions that control accepted geometry as named Fusion user parameters or
   an equivalently inspectable scripted parameter map.
3. Build the smallest analytic feature chain supported by the contract. Use
   shared parameters for symmetry and repetition; keep unrelated features
   independently editable.
4. Keep each independently accepted enclosure, cable, connector, cover, foot,
   insert, or other component as a named component or body until its contract
   passes. Join bodies only when the requested deliverable requires it.
5. For swept flexible parts, record the centerline-length convention, derive the
   end orientation from the path tangent, and check length again from the built
   path or swept volume. Do not use a visually convenient connector pose that
   kinks the path.
6. Treat materials, decals, labels, cameras, lighting, and grid state as visual
   evidence assets. They may improve comparison renders but cannot substitute
   for openings, seams, recesses, ribs, or other geometry required by the
   feature contract.

## Scripted build and recovery

A Fusion API script is useful when the full feature tree must be recreated
repeatably. Keep one build bundle or manifest that hashes the script,
parameters, approved assets, and contract. The build must write an inspectable
status record containing the bundle hash, Fusion version, result document,
feature and body counts, warnings, and export identities.

- A submitted UI command or a visible progress dialog is not completion.
  Verify the result from fresh application state and the status record.
- After any script, parameter, or asset change, every older `.f3d`, export,
  screenshot, and validation result is stale until a successful rebuild.
- Keep the previous accepted document. Apply one feature-local change at a time
  and revert to that checkpoint when topology, unrelated geometry, or the build
  warning count regresses.
- If the host locks, Fusion becomes unresponsive, or control is interrupted,
  stop. Resume by inspecting the current document and status before repeating a
  command; do not infer whether a prior click executed.

## Native verification and exports

1. Require a successful production build with zero build warnings and the
   expected nonzero named feature, component, and body inventories. Query units,
   bounds, volumes, parameters, and critical feature facts from the document.
2. Save the `.f3d`, close the producer session, reopen it in a fresh Fusion
   process, and repeat the inventory and geometry checks. Record this honestly
   as same-kernel Tier 1 validation.
3. Prove editability: change one safe controlling parameter, recompute, verify
   the expected bounded geometry change, restore the original value, recompute,
   and verify the restored facts. Resave only after restoration succeeds.
4. Export STEP from the restored authority and reopen it at the strongest
   available alternate-importer or cross-kernel tier. Verify solid/body count,
   bounds, volumes, analytic surface inventory, radii, continuity, repeated
   transforms, and defining sections.
5. Export one STL per accepted body and validate each separately. A combined
   assembly STL may be kept for whole-model overlays, but coincident interfaces
   can make it non-manifold and it must not replace per-body structural gates.
6. Rerun the fixed local and global point-cloud checks on the built authority or
   its traceable validation sample. A good enclosure score cannot waive a bad
   port, transition, underside feature, cable, or connector.
7. Capture standardized isometric, orthographic, underside, and critical-detail
   views. Side-by-side reference images support topology and visual-fidelity
   review only; appearance cannot waive metrology or editability failures.
8. Hash the final build bundle, `.f3d`, STEP, per-body STLs, screenshots, and
   reports. If any output predates its source bundle, report the build as stale
   rather than complete.

## Completion report

Report the Fusion version, clean-room input manifest when applicable, build
bundle and authority hashes, feature/component/body inventories, warning count,
fresh reopen and edit/restore results, STEP validation tier, per-body STL facts,
local/global evidence, visual-review scope, and every unverified physical claim.
If a required gate fails, return the last accepted Fusion checkpoint and the
smallest next experiment.
