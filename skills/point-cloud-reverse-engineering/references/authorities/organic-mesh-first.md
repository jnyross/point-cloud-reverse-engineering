# Organic mesh-first and STL-only route

Use this route for anatomy, soft or naturally irregular objects, scan-following
shells, and print-fit prototypes when an editable analytic B-rep would
misrepresent the evidence. The authority is deterministic procedural source plus
a validated mesh; STL is a delivery artifact, not proof of physical fit.

Apply the [shared evidence and validation contract](../shared/evidence-and-validation.md).
If the deliverable requires analytic STEP/DWG or manufactured primitive audit,
return to [stack-selection.md](../stack-selection.md) and choose a B-rep route.

## Eligibility gate

Choose mesh-first only when all are true:

- the feature intent is predominantly organic or explicitly scan-following;
- the required authority is procedural mesh/STL, not editable analytic CAD;
- units can be calibrated, or the experiment is labelled non-metric;
- occlusions and missing regions can be identified rather than silently filled;
- requested clearance and wall thickness are explicit parameters.

Keep manufactured inserts, holes, interfaces, datum pads, and fasteners as
separate analytic or parameterised components even when the surrounding shell is
organic.

## Evidence preparation

1. Fingerprint and preserve the full cloud. Record units, normals and confidence,
   scanner poses when available, count, bounds, and calibrated lengths.
2. Register from physical datums or scanner-pose evidence. Measure held-out
   registration residuals and include them in the uncertainty budget.
3. Create separately named fit, fixed-validation, display, and section samples.
   Record every crop, voxel size, outlier rule, and removed count.
4. Orient normals only when neighbourhood and viewpoint evidence supports them.
   Retain a confidence mask; do not use unreliable normals for offsets or angular
   acceptance.
5. Mark holes as intended openings, observed occlusions, or unknown regions.
   A reconstruction algorithm's automatic closure is not topology evidence.

## Surface reconstruction

Select a method from evidence characteristics, then freeze its parameters:

- use screened Poisson only for sufficiently complete, consistently oriented
  normals and inspect where it invents closure outside observed coverage;
- use ball-pivoting or alpha-shape methods for suitable sampling density when
  preserving observed boundaries matters;
- use a bounded voxel/SDF route for robust watertight offsets and shells, while
  reporting resolution-driven form and thickness error;
- use local triangulation or section lofts for controlled partial surfaces when
  global watertight reconstruction would fabricate large missing regions.

Record library versions, method, random seeds, depth/radius/voxel parameters,
crop and confidence masks, and peak resources. Run a coarse canary first. Increase
resolution only when a fixed local metric improves and the declared budget
permits it.

Do not repeatedly smooth until the mesh looks clean. Bound smoothing and compare
critical sections before and after; reject shrinkage, erased landmarks, bridged
openings, and clearance drift.

## Shell and fit construction

1. Define the contact surface, relief regions, trim boundary, insertion direction,
   target clearance, manufacturing allowance, and minimum wall thickness.
2. Derive the inner fit from fixed measurement evidence. Apply clearance as an
   explicit signed offset after accounting for worst inward model error and the
   uncertainty budget.
3. Prefer a robust implicit/SDF shell for complex organic offsets. A naïve vertex-
   normal offset can self-intersect or produce nonuniform thickness at concavities.
4. Preserve intended openings and trim curves. Add outer reinforcement, rounded
   edges, vents, and attachment features parametrically and one at a time.
5. Verify each Boolean at bounded resolution, then recompute topology, local fit,
   thickness, and critical sections. Keep the last accepted source and mesh.

## Local and coverage validation

Use the fixed validation cloud, not the reconstruction input alone.

- Report bidirectional distances on surfaces observable by the scan, with raw
  and area-normalised statistics, coverage cells, exclusions, and uncertainty.
- Compare contact-region and landmark sections in their defining frames using
  bidirectional contour distance and Hausdorff maximum.
- Report reliable normal-angle P95 on smooth observed regions; do not score
  sharp trim boundaries with a smooth-normal gate.
- Sample shell thickness throughout the accepted component and report minimum,
  low percentile, target deviation, and any inaccessible thin regions.
- Check insertion-path interference and explicit relief/clearance regions. A
  static nearest-distance pass does not prove that the object can be inserted.

## Mesh and STL gate

1. Regenerate from an empty process using only the versioned procedural source,
   contract, and immutable evidence identities.
2. Verify units, bounds, plausible volume, connected components, winding, self-
   intersections, zero degenerate faces, and zero non-manifold or boundary edges
   unless an open surface was explicitly requested.
3. Verify no unintended internal shells, tiny disconnected components, filled
   functional openings, or topology changes caused by STL tessellation.
4. Reopen the STL with an alternate importer and repeat dimensions and topology
   facts. Record this as Tier 2 only if the importer path is genuinely distinct.
5. Apply the shared procedural mesh/STL completion gate. Never claim analytic
   editability, printability, comfort, durability, or physical fit from these
   checks alone.

## Physical-fit handoff

When physical fit matters, generate the smallest representative coupon covering
the highest-risk contact/clearance section before a full print. Provide the
coupon geometry and measured intent, but do not slice, purchase, or start a print
unless a separate authorized workflow does so. Record observed coupon fit and
feed an approved clearance change back into the versioned procedural source.
