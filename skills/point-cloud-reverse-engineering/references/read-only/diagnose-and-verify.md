# Diagnose, recover, and verify without mutation

## Evidence ledger

Before changing anything, record:

- the last known-good artifact;
- the current source type, format, units, point count, and bounds;
- the exact application, version, command, and observed failure;
- every reversible experiment and its result;
- which conclusions are observed, inferred, or still unknown.

This route makes no state changes. Every action described below is a proposed
next scoped experiment, not an instruction to execute it here. Report one small
canary at a time and require an ineffective change to be reversed before a later
hypothesis. If repair is authorized, return through the scoped operating route
with the last verified checkpoint and one bounded change.

## Common failure branches

### The source is a mesh

Report the primary evidence as missing and propose obtaining the fused cloud from
the original scan project or scanner export. A mesh may remain secondary visual
evidence but must not silently replace the cloud.

### A proprietary desktop application is unavailable

Do not treat that as a geometry failure or silently substitute a scan-following
mesh. Propose the [Linux open-source route](../linux-open-source.md) only when it
is acceptable: CloudCompare for the cloud and bundled analytic `$cad` for STEP
and derived STL, with unchanged gates. Otherwise report the smallest manual
handoff for the chosen application.

### ASC imports incorrectly

Propose a bounded import canary that explicitly maps `X Y Z Nx Ny Nz` and checks
whitespace, skipped lines, scale, point count, and dimensions. State that an
implausible result must be rejected.

### Units or scale are only plausible, not calibrated

Do not choose units from object plausibility or a host default. Inspect scanner
metadata and independent calibrated lengths, then apply the unit-calibration
gate in the [shared evidence contract](../shared/evidence-and-validation.md).
Until the scale factor and its uncertainty are verified, classify metric fit,
clearance, and manufacturing claims as inconclusive.

### CloudCompare displays primitives but not the cloud

Propose a reversible two-part canary: create a native primitive and open a known
cloud. If only the cloud fails, inspect entity visibility, scalar-field/display
state, and preferences. Require a preference backup before any later reset;
reinstallation is not first-line evidence.

### E57 fails in BricsCAD

Propose preserving E57 and exporting LAS from the aligned cloud in the scoped
route. Removing normals is a diagnostic experiment, not a guaranteed fix.
Success requires LAS caching/display plus plausible count and extents.

### A crop is fuzzy or empty

Diagnose both thickness and view direction. Narrower is not always crisper: an
undersampled crop can be unusable, while a wide crop mixes surfaces. Propose
small reversible thickness steps viewed normal to the cut.

### A manufactured corner looks faceted or over-rounded

Identify the affected feature: footprint corner, top/bottom perimeter transition,
or shaded display. From existing wire/section/kernel evidence, distinguish an
analytic arc or spline, segmented polyline, solid edge treatment, and display
tessellation. Recommend changing only the diagnosed layer in a later scoped
route. A 3D edge fillet is not a remedy for footprint-corner faceting.

### The entity count is correct but the feature topology is wrong

Inspect the feature-intent contract and existing defining views. Diagnose
unintended fillet or chamfer faces even when entity count is correct, then
recommend restoring the last accepted body or replacing only the rejected
feature through the scoped route.

### The global distance score passes but a critical feature looks wrong

Treat the visible defect as evidence, not a cosmetic objection. Assess the
feature's defining-frame evidence, raw and area-normalised residuals, primitive
chain, continuity, surfaces, and radii. A dense flat region can dominate a
global score. Recommend replacing only the rejected feature and rerunning both
fixed local and whole-model checks later.

### A numerical validation exhausts memory or destabilizes the workstation

Report the run as failed or unavailable, not passed, and do not recommend a
larger retry. Propose bounded batches, thread caps, the same fixed mask, and
sampled reverse distances where exhaustive queries would score unobserved faces.

### The residual passes but evidence uncertainty is larger than tolerance

Keep the residual, registration repeatability, scale uncertainty, sampling
sensitivity, segmentation sensitivity, and query tolerance separate. Recompute
the metrology budget in the
[shared evidence contract](../shared/evidence-and-validation.md). Report the
result as inconclusive when evidence uncertainty is not smaller than the
declared tolerance; do not add clearance silently to manufacture a pass.

### Cloud-to-model passes but unsupported geometry remains

Assess model-to-cloud coverage only on surfaces observable from the scan and
label closure or occluded faces. Inspect area-normalised coverage, reliable
normal angles, defining-section contours, and feature-specific parameters. A
dense observed plane can conceal an unsupported wall, missing opening, or wrong
axis in a one-direction nearest-distance score.

### The file reopens but the validation is not independent

Identify whether the reopen used the producer session, a fresh process with the
same importer/kernel, an alternate importer, or a cross-kernel consumer. Apply
the validation tiers in the
[shared evidence contract](../shared/evidence-and-validation.md) and report only
the strongest tier completed. A fresh same-kernel process proves persistence,
not independent interchange.

### Blender becomes unusable with the evidence cloud

Diagnose whether measurement and display density were conflated. Recommend
keeping the fixed full or bounded numerical cloud in Open3D/CloudCompare and
creating a separately named voxel sample only in the later scoped route. Never
accept validation against only the display sample.

### CAD Sketcher works interactively but fails headlessly

Record the exact Blender and extension versions and propose one small native
sketch/extrude canary. Some UI operators assume an active interactive tool or
preloaded node asset. Prefer the add-on's supported UI/operator path; for a
deterministic headless benchmark, use its native data model only when documented
or verified by a canary, preload only the asset shipped by that version before
invoking the normal feature operator, and record the integration path. Do not
patch installed extension source merely to make the benchmark pass.

### A Blender Curves body renders but will not convert for validation

Do not recommend destructive conversion of the authority. Propose duplicating
the native Curves object/data in the scoped route, evaluating only that isolated
copy, and repeating the canary after a fresh-process reopen.

### The Blender agent bridge is unavailable

Confirm that the matching add-on version is enabled, the bridge is explicitly
started, it binds only to loopback, and the MCP client configuration points to
the same URL and runtime. Exercise a read-only scene-inspection tool before any
mutation. A client configured or updated mid-session may require a new client
session; do not treat that lifecycle boundary as a geometry failure.

### The Blender result looks editable but the deliverable requires STEP

A native `.blend` or evaluated mesh is an intermediate workbench artifact, not
an editable B-rep handoff. Recommend a scoped handoff of the accepted alignment
and contract to OpenCascade/`$cad` or another STEP authority, followed by fixed
local and whole-model checks on that STEP.

### The CAD source is shorter but the model is not simpler

Inspect the executed feature graph. Count emitted primitives, profiles, Boolean operations, pattern instances, placements, and independent parameters; loops and helpers can hide the same or greater kernel work behind fewer lines. Keep a source-only refactor only when it improves editability, and do not report it as geometric compression.

### A simplification passes the global comparison but changes a repeated feature

Inspect existing defining-section evidence for every instance. A default pattern
may rotate an asymmetric feature while coarse facts pass. Diagnose the candidate
as rejected and recommend restoring the last accepted construction before later
equivalence checks.

### A loft is degenerate or distorted

Check existing profiles for degeneracy, separation, ordering, and intended
planes. Propose a bounded three-profile/no-rail canary, with an intermediate
profile or minimum rails only where overlay evidence proves a need.

### Adjacent surface patches will not stitch

Diagnose whether both patches reuse the exact same seam. Propose `DELOBJ=0` and a
two-patch stitch canary before any later large quilt.

### Thicken goes the wrong way or fails

Recommend reverting the failed attempt. Propose a small one- or two-patch canary
that checks surface side/normal and entity type before a later quilt extension.

### Export looks complete but is invalid

Diagnose selection/export scope from existing facts. Propose explicit-body
re-export followed by CAD/STL bounds, volume, triangle, degeneracy, boundary,
manifold, and winding checks in the scoped route.

## Diagnostic completion gate

Call the diagnosis complete only when:

1. the original source still exists unchanged;
2. every application handoff has recorded units, point count, and bounds;
3. the intended primitive chain and continuity of every critical feature have an explicit `pass`, `fail`, `inconclusive`, or `unknown` status grounded in the available defining views and CAD or kernel evidence;
4. every critical feature's local-distance gate has an explicit status, and global statistics do not conceal or override a local failure or inconclusive result;
5. the fixed whole-model mask, exclusions, directionality, percentiles, maximum outliers, and resource use are reported without claiming that a percentage threshold means every point passed;
6. the declared authority and deliverables are identified without treating
   STEP/DWG, BLEND, replayable OCCT, and STL-only contracts as interchangeable;
7. the strongest completed validation tier is named honestly;
8. the applicable authority gate in the
   [shared evidence contract](../shared/evidence-and-validation.md) is either
   evidenced or listed as the next test;
9. any untested clearance, printability, or physical fit is labelled unverified.

If any item fails, report the last verified checkpoint and the smallest next experiment. Do not claim completion from a successful command submission or a plausible screen alone.
