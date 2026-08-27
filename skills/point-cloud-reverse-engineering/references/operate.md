# Scoped construction dispatcher and desktop CAD playbook

## Dispatch before loading host details

Apply the [shared evidence and validation contract](shared/evidence-and-validation.md)
and declare the authority before construction. Then dispatch once:

- native Blender/CAD Sketcher authority or Blender workbench: read
  [blender-ai-workbench.md](authorities/blender-ai-workbench.md) and stop here;
- replayable browser/OCCT authority: read
  [browser-occt-workbench.md](authorities/browser-occt-workbench.md) and stop here;
- organic procedural mesh or STL-only authority: read
  [organic-mesh-first.md](authorities/organic-mesh-first.md) and stop here;
- Linux/open-source analytic B-rep authority: read
  [linux-open-source.md](linux-open-source.md) and stop here;
- CloudCompare plus BricsCAD/desktop authority: continue below.

If authority is not fixed, do not begin construction. Use the read-only
[stack-selection.md](stack-selection.md) decision matrix and return with a
proposed authority and deliverables. Do not treat a `.blend`, browser preview,
replayable OCCT chain, editable STEP/DWG, and STL-only mesh as interchangeable.

## Desktop checkpoint

1. Complete every preconstruction gate in the shared contract, including source
   identity, unit calibration, alignment, uncertainty budget, feature contract,
   fixed masks, local/global tolerances, and resource limits.
2. Classify each feature as scan-following fit, design-intent geometry, freeform
   skin, or section-controlled solid. Keep components separate through overlay
   acceptance and instance repeated manufactured features from shared parameters.
3. Preserve raw fitted values beside regularised dimensions. Treat clearances
   and wall thicknesses as explicit tunable values, not tutorial defaults.

## CrealityScan to CloudCompare

1. Complete point-cloud processing, fusion, and restrained cleanup in CrealityScan. Preserve edges and mating surfaces.
2. Export the fused **point cloud** as ASC. Do not choose a mesh export for the primary handoff.
3. Open the ASC in CloudCompare. For a six-column scanner export, map the fields to `X`, `Y`, `Z`, `Nx`, `Ny`, `Nz`, use whitespace separation, skip zero header lines, and keep scale at 1 unless independent evidence proves another scale.
4. Confirm CloudCompare identifies the entity as a cloud, not a mesh. Record its point count and bounding dimensions.
5. Clone the cloud and align the clone from physical datums:
   - level a known flat datum to XY;
   - assign a meaningful long or symmetry axis to X;
   - assign width to Y and height to Z;
   - move a documented datum or centre near the origin.
6. Verify top, front, side, and isometric views. A visually tidy bounding-box alignment is not a substitute for manufactured datums.
7. Recheck point count and bounds. Rotation may change axis-aligned bounds; scale and point count must remain explainable.
8. Save a separately named E57 archive when useful. Export a separately named LAS for BricsCAD, because LAS is the reliable point-cloud interchange for this workflow.

For a hand plane, the sole is the XY datum, heel-to-toe is X, width is Y, and the tote and knob rise in positive Z. The perpendicular side planes disambiguate the width axis.

## CloudCompare to BricsCAD

1. Start from a millimetre 3D drawing.
2. Import the aligned LAS and allow BricsCAD to build its cache.
3. Confirm the cloud displays, then compare point count and extents with the CloudCompare handoff.
4. Use a dark or X-ray display, bright cloud colours, and a small point size. Keep sketches and solids on contrasting layers.
5. Enable ordinary object snaps as needed. Enable point-cloud 3D snapping only while placing geometry on cloud evidence.
6. Preserve the full cloud and create reversible crops. Never erase the only copy of the cloud from the drawing.

## Choose the construction method

### A. Thin local crops and section-controlled lofts

Use for elongated forms whose cross-section changes along an axis.

1. Crop a thin band at a meaningful form change.
2. View normal to the crop plane so the screen shows the true cross-section.
3. Calibrate crop thickness to point density: too thin is sparse; too wide blurs the edge.
4. Place a local UCS on the visible cut using three reliable cloud points.
5. Trace a clean, closed profile on UCS XY. Prefer lines and arcs for designed geometry and use the fewest spline points that preserve real freeform curvature.
6. Repeat only at curvature changes, bumps, openings, or sharp transitions.
7. Test a loft with about three corresponding profiles and no rails first.
8. Add the minimum 3D spline rails only where the loft flattens, hooks, or misses the cloud.
9. Split real sharp edges into separate lofts. Join solids only after each segment passes overlay inspection.

### B. Direct splines, surface patches, stitch, and thicken

Use for a coherent curved skin. Do not use it to imitate planar manufactured regions.

1. Enable point-cloud nearest 3D snapping and draw the outer boundary with deliberate 3D `SPLINE` fit points.
2. Regularise portions intended to be straight or smooth instead of following isolated noise.
3. Split the region where curvature changes materially. One large closed loop is a planning boundary, not a finished surface.
4. Draw cross-section splines and longitudinal guide rails on the cloud. Flat areas need few rails; curved areas get only the additional rails required to control the loft.
5. Set `DELOBJ=0` so an early loft does not consume a boundary required by its neighbour.
6. Run `LOFT`, choose a surface result, and supply guide rails.
7. Reuse the exact same boundary spline at adjacent patch seams. Nearly coincident duplicate curves are not reliable seams.
8. Run `DMSTITCH` as soon as two patches exist. Confirm they become one `SURFACE` before extending the quilt.
9. Run a small reversible `DMTHICKEN` canary. Confirm thickness direction relative to the fit surface and verify the result is a `3DSOLID`.
10. Extend only after the canary succeeds, then inspect the complete quilt against the cloud from several views.

### C. Scan-following fitted holder

Use when the measured perimeter itself is the fit requirement.

1. Isolate a narrow point band around the contact datum.
2. Trace one closed planar fit profile through reliable envelope evidence. Regularise deliberately manufactured straight portions.
3. Offset the profile outward by an explicit, tunable clearance.
4. Offset again for the holder wall or perimeter.
5. Convert closed profiles to regions, extrude the outer region to the base depth, extrude the pocket cutter to the recess depth, and subtract.
6. Verify the recess opening, floor thickness, and final entity type. Preserve source profiles for tuning.

### D. Analytic design-intent part or holder

Use when symmetry, tangency, uniformity, or manufacturability matters more than copying local scan noise.

1. Start with the smallest justified topology hypothesis, such as `plane -> tangent torus -> cylinder`, rather than fitting an unconstrained surface first.
2. Fit parameters from defining sections or surface bands. Use spatial or area-normalized samples when raw scan density would overweight repeatedly observed regions.
3. Preserve the unconstrained fitted values, then regularise deliberately to plausible manufactured dimensions. Recompute the local residuals and report whether regularisation improved or traded away fit.
4. Enforce intended relationships explicitly: parallel sides, equal opposite dimensions, shared radii, repeated instances, symmetry, and tangency.
5. Keep the editable analytic CAD construction authoritative. Do not import a scan-following mesh into Booleans or surface construction merely because it scores well numerically.
6. Compare each primitive chain with the sampled envelope and quantify inward error, gaps, percentile residuals, and worst local deviation.
7. Treat idealisation error and physical clearance separately. Clearance must cover the worst inward modelling error plus a tunable manufacturing allowance.
8. Build with direct primitives, profiles, extrusions, subtractions, and analytic fillets where supported. Use splines or freeform surfaces only for features whose contract requires them.

## Simplify an accepted analytic reconstruction

Use this pass only after the analytic baseline satisfies its feature-intent and fit gates.

1. Freeze the accepted source, exports, alignment, masks, exclusions, local sections, rendered views, tolerances, and surface inventory. Set an iteration limit and memory/thread budget before experimenting.
2. Optimise the executed feature graph, not lines of source: count primitives, profiles, Boolean operations, expanded pattern instances, placements, and independent parameters. A loop or helper that emits the same kernel operations is a readability refactor, not geometric compression.
3. Change one modelling idea at a time. Prefer shared profiles and dimensions, symmetry, orientation-preserving patterns, revolved or swept cuts, and compound Booleans. Couple parameters only when the feature-intent evidence says they are truly shared.
4. Accept a candidate only when solid validity, bounds, volume, analytic surface classes, radii, continuity, critical sections, rendered feature views, and fixed point-cloud results remain equivalent. Claim exact identity only when the kernel proves topological and geometric equality without a tolerance-based approximation. A tolerance-bounded Boolean symmetric-difference check supports only tolerance-equivalence, which still requires the full local and global gates.
5. Check every repeated instance's placement and orientation locally. Global geometry or a coarse STEP comparison can miss an asymmetric pad, port, or recess rotated by a default polar pattern.
6. Treat STL triangle counts and mesh-to-mesh differences as diagnostics because tessellation can vary for unchanged analytic geometry. Compare the authoritative STEP or kernel solid, then regenerate and structurally validate the STL.
7. Keep an accept/reject ledger with the candidate, one change, feature-graph cost delta, gate results, and reason. Revert rejected candidates and stop at the declared iteration limit.

## Desktop verification and export

1. Keep the previous accepted artifact and modify only the rejected feature.
   Compare bounds, datums, entity/topology counts, and unrelated geometry before
   accepting the change.
2. Toggle the measurement cloud or bounded fixed evidence after every major body
   and inspect orthographic, defining-section, close-up, and isometric overlays.
3. Query the live drawing after each operation. Confirm intended `SPLINE`,
   `LOFTEDSURFACE`, `SURFACE`, `REGION`, and `3DSOLID` counts, primitive chains,
   radii, constraints, continuity, and repeated-feature transforms.
4. Apply every semantic-surface, normal, coverage, section-contour, local, global,
   uncertainty, and resource gate in the shared contract. Appearance and a
   whole-model pass cannot waive a critical-feature failure.
5. Keep sketches, components, and construction bodies until comparison passes.
   Save STEP/DWG to a new path and apply the editable STEP/DWG authority gate at
   the strongest available validation tier.
6. Derive a requested STL from the accepted body and apply its structural and
   dimensional checks. State that printability and physical fit remain unproved.
7. For hybrid work, verify the production model consumed the exact accepted
   alignment, masks, raw fits, regularised values, and tolerances; validate the
   production artifact rather than only its Blender or browser preview.
