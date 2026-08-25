# Point-cloud reverse-engineering operator playbook

## Checkpoint 0: establish the source and target

1. Record the source path, format, point count, units, bounds, intended object, fit surfaces, and requested design intent.
2. Confirm the primary source is a point cloud. If it is a mesh and a cloud exists, stop and obtain the cloud.
3. Preserve the scan project and original export. Work only on a clone or separately named copy.
4. Classify each important feature, not merely the whole part:
   - **scan-following fit** for a recess or mating surface that must follow measured evidence;
   - **design-intent geometry** for straight, symmetric, tangent, cylindrical, planar, or otherwise manufactured features;
   - **freeform skin** for a curved surface governed by splines in two directions;
   - **section-controlled solid** for a long form whose cross-section changes along an axis.
5. Record a compact feature-intent contract for each manufactured transition: component, defining view or axis, primitive chain, intended G0/G1/G2 continuity, shared dimensions or symmetry, dimensional evidence, topology evidence, exclusions, and confidence. Treat footprint corner radii and top/bottom perimeter transitions as independent features. Use a sharp transition when no evidence supports a fillet or chamfer.
6. Keep distinct components such as enclosures, cables, fasteners, and holders as separate solids and layers through overlay acceptance. Union them only when the requested final output requires one body.
7. Record clearances and thicknesses as tunable design values. Do not derive them silently from tutorial examples.
8. Assign evidence roles explicitly: use the point cloud or calibrated specifications for dimensions; use close-up photographs and product references for feature identity, topology, and continuity unless they contain scale evidence; use repetition and symmetry as manufacturing-intent evidence.
9. Define acceptance before construction: global and critical-feature tolerances, permitted exclusions, cloud-to-CAD versus CAD-to-cloud direction, required percentiles and maximums, and a safe memory/thread budget.
10. For repeated manufactured features, use one shared parametric definition and instance it unless the evidence supports real variation.

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
4. Accept a candidate only when solid validity, bounds, volume, analytic surface classes, radii, continuity, critical sections, rendered feature views, and fixed point-cloud results remain equivalent. When claiming identical geometry, require an exact CAD-kernel or B-rep symmetric-difference check; otherwise describe the result as tolerance-equivalent and rerun the full local and global gates.
5. Check every repeated instance's placement and orientation locally. Global geometry or a coarse STEP comparison can miss an asymmetric pad, port, or recess rotated by a default polar pattern.
6. Treat STL triangle counts and mesh-to-mesh differences as diagnostics because tessellation can vary for unchanged analytic geometry. Compare the authoritative STEP or kernel solid, then regenerate and structurally validate the STL.
7. Keep an accept/reject ledger with the candidate, one change, feature-graph cost delta, gate results, and reason. Revert rejected candidates and stop at the declared iteration limit.

## Verification and export

1. Keep the previous accepted artifact and modify only the rejected feature. Compare old and new CAD bounds, major datums, topology counts, and unrelated geometry before accepting the change.
2. Toggle the full point cloud on after every major body and inspect orthographic, defining-section, close-up, and isometric views.
3. Query the live drawing or CAD kernel after each material operation. Confirm expected analytic surfaces, `SPLINE`, `LOFTEDSURFACE`, `SURFACE`, `REGION`, and `3DSOLID` counts rather than trusting appearance alone.
4. Walk the feature-intent contract. For each critical feature, verify the primitive chain, radii, repeated constraints, and intended sharp, G1 tangent, smoothly curved, or chamfered transitions. Reject unintended cones, planar bevels, splines, or step faces even when the model looks close.
5. Compute a feature-local distance check in the feature's defining frame. Report the evaluated point/cell count, within-tolerance percentage, P95/P98, mean when useful, and maximum residual. Use area-normalized results as a companion to raw point statistics when density is uneven.
6. Compute the whole-model check separately using a fixed, documented mask and exclusions. Report cloud-to-CAD and CAD-to-cloud directions separately; label hidden or unobserved CAD closure faces rather than silently treating them as measured fit surfaces.
7. A global threshold cannot waive a failed critical-feature topology or local-distance check. Likewise, a visually convincing screenshot cannot waive the numerical and analytic checks.
8. Preserve raw fitted values alongside regularised parameters and record the resulting fit change.
9. Run distance calculations in bounded batches with controlled numerical-library threads. Avoid unnecessarily dense construction meshes, record peak process memory, and stop rather than retrying an approach that destabilizes the workstation.
10. Keep sketches, separate component solids, and construction bodies until comparison passes.
11. Save the editable STEP or DWG to a new path, reopen it with an independent reader or CAD kernel, and verify solid validity, volume, bounds, surface classes, and zero unsupported freeform surfaces.
12. Export the selected final body as a suitably tessellated STL when a mesh is requested. Independently verify dimensions, plausible volume, nonzero triangles, zero degenerate triangles, zero boundary and non-manifold edges, and consistent winding.
13. State what remains unproved. CAD and STL checks do not prove printer-bed suitability, printed accuracy, physical fit, or service performance.
