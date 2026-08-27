# Diagnose, recover, and verify

## Evidence ledger

Before changing anything, record:

- the last known-good artifact;
- the current source type, format, units, point count, and bounds;
- the exact application, version, command, and observed failure;
- every reversible experiment and its result;
- which conclusions are observed, inferred, or still unknown.

Run one small canary at a time. Reverse an ineffective change before trying the next hypothesis.

## Common failure branches

### The source is a mesh

Stop. Return to the original scan project or scanner export and obtain the fused point cloud. A mesh can remain secondary visual evidence but must not silently replace the cloud.

### A proprietary desktop application is unavailable

Do not treat that as a geometry failure or silently substitute a scan-following mesh. If Linux or open-source tools are acceptable, switch to the [Linux open-source route](linux-open-source.md): CloudCompare for the cloud and the bundled analytic `$cad` stack for STEP and derived STL. Preserve the same alignment, local-feature, topology, tolerance, and resource gates. Otherwise give the smallest precise manual handoff for the user's chosen application.

### ASC imports incorrectly

Reopen the import table and map `X Y Z Nx Ny Nz` explicitly. Confirm whitespace, skipped lines, and scale. Reject the import if point count or dimensions are implausible.

### CloudCompare displays primitives but not the cloud

Use a reversible two-part canary: create a native primitive and open a known cloud. If only the cloud fails, inspect entity visibility, scalar-field/display state, and preferences. Back up preferences before a reset. Reinstalling the application is not first-line evidence and must be reversed if it changes nothing.

### E57 fails in BricsCAD

Preserve the E57 archive and export LAS from the aligned cloud. Removing normals is a diagnostic experiment, not a guaranteed fix. Success means the LAS caches, displays, and preserves plausible point count and extents.

### A crop is fuzzy or empty

Check both thickness and view direction. Narrower is not always crisper: an undersampled crop can be unusable, while a wide crop mixes surfaces. Adjust thickness in small reversible steps and view normal to the cut.

### A manufactured corner looks faceted or over-rounded

Identify the affected feature before changing geometry: footprint corner, top/bottom perimeter transition, or shaded display. Inspect a wireframe or edge view and a section normal to the suspected edge, then query whether the boundary is an analytic arc or spline, a segmented polyline, or a filleted or chamfered solid edge. Fix the diagnosed layer: adjust display tessellation reversibly when the analytic geometry is sound, rebuild a segmented footprint with the simplest justified analytic primitive, or apply a measured edge treatment only when the feature-intent contract supports it. A 3D edge fillet is not a remedy for footprint-corner faceting.

### The entity count is correct but the feature topology is wrong

Return to the feature-intent contract and inspect every transition in its defining orthographic or section view. Reject unintended fillet or chamfer faces even when the drawing contains the expected number of solids. Restore the last accepted body or replace only the rejected feature, repeat the overlay and topology checks, then save and reopen the corrected DWG.

### The global distance score passes but a critical feature looks wrong

Treat the visible defect as evidence, not as a cosmetic objection. Isolate the feature in its defining frame, compare raw and area-normalized local residuals, inspect the intended primitive chain and continuity, and query the CAD surface types and radii. A dense flat region can dominate a global score while a port, opening, or corner remains malformed. Replace only the rejected feature, then rerun both the local check and the fixed whole-model comparison.

### A numerical validation exhausts memory or destabilizes the workstation

Stop the process and do not retry the same route at a larger scale. Use bounded point batches, cap numerical-library threads, reuse a fixed mask, and sample diagnostic reverse distances when hidden or unobserved CAD faces make an exhaustive reverse query misleading. Record peak memory and distinguish an unavailable check from a passing result.

### Blender becomes unusable with the evidence cloud

Separate measurement density from display density. Keep the fixed full or
bounded numerical cloud in Open3D/CloudCompare for fitting and validation, and
create a separately named voxel sample for Blender display. Record both point
counts and voxel sizes. Do not rename the display sample as if it were the
measurement cloud, and never validate against only the display sample.

### CAD Sketcher works interactively but fails headlessly

Record the exact Blender and extension versions and reproduce one small native
sketch/extrude canary. Some UI operators assume an active interactive tool or
preloaded node asset. Prefer the add-on's supported UI/operator path; for a
deterministic headless benchmark, use its native data model only when documented
or verified by a canary, preload only the asset shipped by that version before
invoking the normal feature operator, and record the integration path. Do not
patch installed extension source merely to make the benchmark pass.

### A Blender Curves body renders but will not convert for validation

Do not destructively convert the authority. Duplicate the native Curves object
and its data, convert the isolated copy with the evaluated modifier stack, run
mesh/topology checks on that copy, and remove it afterwards. Reopen the saved
`.blend` in a fresh process and repeat the conversion canary.

### The Blender agent bridge is unavailable

Confirm that the matching add-on version is enabled, the bridge is explicitly
started, it binds only to loopback, and the MCP client configuration points to
the same URL and runtime. Exercise a read-only scene-inspection tool before any
mutation. A client configured or updated mid-session may require a new client
session; do not treat that lifecycle boundary as a geometry failure.

### The Blender result looks editable but the deliverable requires STEP

A native `.blend` or evaluated mesh is an intermediate workbench artifact, not
an editable B-rep handoff. Export the accepted alignment and feature contract,
regenerate the solid through OpenCascade/`$cad` or another declared STEP
authority, then repeat local and whole-model distance checks on that STEP.

### The CAD source is shorter but the model is not simpler

Inspect the executed feature graph. Count emitted primitives, profiles, Boolean operations, pattern instances, placements, and independent parameters; loops and helpers can hide the same or greater kernel work behind fewer lines. Keep a source-only refactor only when it improves editability, and do not report it as geometric compression.

### A simplification passes the global comparison but changes a repeated feature

Inspect every instance in its defining section and verify its transform and orientation. Default circular or mirrored patterns may rotate an asymmetric foot, port, pad, or recess while leaving global bounds, volume, or coarse STEP distances apparently acceptable. Reject the candidate, restore the last accepted feature construction, and repeat the exact or local equivalence checks.

### A loft is degenerate or distorted

Check that profiles are nondegenerate, meaningfully separated, similarly ordered, and placed on intended planes. Start with three corresponding profiles and no rails. Add an intermediate profile or minimum guide rails only where the overlay proves a need. Use direct solids for planar regions.

### Adjacent surface patches will not stitch

Confirm both patches reuse the exact same seam curve. Set `DELOBJ=0` before rebuilding. Stitch two patches early; do not construct a large quilt on an unproved seam.

### Thicken goes the wrong way or fails

Undo it. Run a small, single-patch or two-patch canary, inspect the surface normal/side, and retry with a small thickness. Do not extend the quilt until entity inspection confirms a `3DSOLID`.

### Export looks complete but is invalid

Select the final body explicitly and re-export. Compare CAD and STL bounds and volume. Reject meshes with zero triangles, degenerates, open boundaries, non-manifold edges, or inconsistent winding.

## Completion gate

Call the workflow complete only when:

1. the original source still exists unchanged;
2. every application handoff has recorded units, point count, and bounds;
3. the intended primitive chain and continuity of every critical feature are confirmed from a defining section or orthographic view and from the CAD entities or kernel surface types;
4. every critical feature passes its declared local-distance gate, and global statistics do not conceal a local failure;
5. the fixed whole-model mask, exclusions, directionality, percentiles, maximum outliers, and resource use are reported without claiming that a percentage threshold means every point passed;
6. the separately named editable STEP or DWG exists and reopens cleanly;
7. any requested STL passes structural and dimensional checks;
8. any untested clearance, printability, or physical fit is labelled unverified.

If any item fails, report the last verified checkpoint and the smallest next experiment. Do not claim completion from a successful command submission or a plausible screen alone.
