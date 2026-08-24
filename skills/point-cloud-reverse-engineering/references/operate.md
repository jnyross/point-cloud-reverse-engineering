# Point-cloud reverse-engineering operator playbook

## Checkpoint 0: establish the source and target

1. Record the source path, format, point count, units, bounds, intended object, fit surfaces, and requested design intent.
2. Confirm the primary source is a point cloud. If it is a mesh and a cloud exists, stop and obtain the cloud.
3. Preserve the scan project and original export. Work only on a clone or separately named copy.
4. Decide which result is wanted:
   - **scan-following fit** for a recess or mating surface that must follow measured evidence;
   - **design-intent geometry** for straight, symmetric, tangent, cylindrical, planar, or otherwise manufactured features;
   - **freeform skin** for a curved surface governed by splines in two directions;
   - **section-controlled solid** for a long form whose cross-section changes along an axis.
5. Record a compact feature-intent contract for each manufactured transition: component, defining view or axis, target primitive or continuity, edge treatment, supporting scan or user evidence, and confidence. Treat footprint corner radii and top/bottom perimeter transitions as independent features. Use a sharp transition when no evidence supports a fillet or chamfer.
6. Keep distinct components such as enclosures, cables, fasteners, and holders as separate solids and layers through overlay acceptance. Union them only when the requested final output requires one body.
7. Record clearances and thicknesses as tunable design values. Do not derive them silently from tutorial examples.

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

### D. Design-intent holder or regularised part

Use when symmetry, tangency, uniformity, or manufacturability matters more than copying local scan noise.

1. Fit the simplest justified primitive: lines and tangent arcs, rounded rectangle, circle, cylinder, plane, or a small controlled spline set.
2. Enforce intended relationships explicitly: parallel sides, equal opposite dimensions, shared radii, symmetry, and tangency.
3. Compare the primitive with the sampled envelope and quantify inward error and gaps.
4. Treat idealisation error and physical clearance separately. The clearance must cover the worst inward modelling error plus a tunable manufacturing allowance.
5. Build the recess and body with the same region, extrusion, and subtraction sequence as the fitted holder.
6. Report the predicted minimum, typical, and maximum gaps. Larger local gaps may be the deliberate cost of regularisation.

## Verification and export

1. Toggle the full point cloud on after every major body and inspect orthographic plus isometric views.
2. Query the live drawing after each material operation. Confirm expected `SPLINE`, `LOFTEDSURFACE`, `SURFACE`, `REGION`, and `3DSOLID` counts rather than trusting appearance alone.
3. Walk the feature-intent contract. View each transition normal to its defining plane or in section, confirm the intended sharp, rounded, tangent, or chamfered form, and reject unintended edge faces. A correct entity count does not satisfy this check.
4. Keep sketches, separate component solids, and construction bodies until comparison passes.
5. Save to a new DWG path, reopen it, and ensure no unsaved drawing changes remain.
6. Export the selected final body as a high-quality binary STL when a printable mesh is requested.
7. Independently verify dimensions, plausible volume, nonzero triangles, zero degenerate triangles, zero boundary and non-manifold edges, and consistent winding.
8. State what remains unproved. CAD and STL checks do not prove printer-bed suitability, printed accuracy, physical fit, or service performance.
