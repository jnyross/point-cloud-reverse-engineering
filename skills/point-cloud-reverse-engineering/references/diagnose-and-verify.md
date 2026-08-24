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

Stop. Return to CrealityScan and export the fused point cloud. A mesh can remain secondary visual evidence but must not silently replace the cloud.

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
3. the intended CAD entity chain and every feature-intent transition are confirmed from live state;
4. the separately named DWG exists and reopens cleanly;
5. any requested STL passes structural and dimensional checks;
6. any untested clearance, printability, or physical fit is labelled unverified.

If any item fails, report the last verified checkpoint and the smallest next experiment. Do not claim completion from a successful command submission or a plausible screen alone.
