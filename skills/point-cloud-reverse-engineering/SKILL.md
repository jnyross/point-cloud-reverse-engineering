---
name: point-cloud-reverse-engineering
description: Turns fused 3D-scan point clouds and supporting photographs into verified scan-following or analytic design-intent CAD, with reversible recovery, feature-local fit checks, and evidence-gated STEP, DWG, or STL exports.
---

# Point Cloud Reverse Engineering

## Trigger
- Turn this fused CrealityScan point cloud into an aligned BricsCAD model and verify the exported STL.
- Align this ASC point cloud in CloudCompare with the sole down and export a BricsCAD-compatible LAS.
- Trace splines directly on this point cloud, loft the surface patches, stitch them, and thicken the result.
- Build a fitted holder with a recessed seat from this scanned object while preserving the source scan.
- Reconstruct this manufactured enclosure as editable analytic STEP geometry, using close-up photographs to resolve feature topology and the point cloud for dimensions.
- Compress this accepted analytic reconstruction into the smallest editable feature program without changing its geometry, feature intent, or scan-validation result.
- Diagnose why this CloudCompare or BricsCAD point-cloud workflow failed, reverse ineffective changes, and recover the last verified state.

## Non-triggers
- Repair or slice this STL mesh without using a point cloud.
- Create an ordinary CAD part that has no scan or point-cloud evidence.
- Summarize these YouTube videos without applying the demonstrated reverse-engineering workflow.
- Recommend a scanner, printer, or CAD package to buy.
- Start, monitor, or operate a physical 3D print.

## Inputs
A fused point cloud in ASC, E57, or LAS form, raw or already aligned; the user must also state the object or design intent and any fit, clearance, symmetry, or regularity requirements. Close-up photographs or product references may resolve feature identity, topology, and continuity, but are not dimensional evidence unless independently calibrated. A mesh may be secondary evidence but is not the primary source when a point cloud is available.

## Mutation policy
scoped: only the requested model or rejected feature.

## Verification
- Identify whether every source is a point cloud or mesh and preserve the original source unchanged.
- Verify units, scale, orientation, point count, and bounding dimensions after each application handoff.
- Treat reconstruction as topology selection followed by parameter fitting: choose the simplest manufactured primitive chain supported by the evidence, then fit and regularise its dimensions.
- Verify every critical feature locally as well as the model globally. A good whole-model distance score never overrides malformed ports, corners, openings, or transitions.
- Verify topology and database state: confirm each intended sharp, G1 tangent, smoothly curved, or chamfered transition in its defining view or section, then audit the exported CAD surface types, radii, continuity, repeated constraints, and entity counts.
- When simplifying an accepted analytic model, measure the executed feature graph rather than source length and accept a candidate only when geometry, analytic surfaces, repeated-feature orientation, local sections, and fixed point-cloud results remain equivalent.
- Save the editable STEP or DWG to the stated path, confirm it reopens, and confirm no uncommitted drawing changes remain before completion.
- For STL output, verify plausible dimensions and volume, nonzero triangle count, zero degenerate triangles, zero boundary and non-manifold edges, and consistent winding.
- Run large distance checks in bounded batches with controlled thread counts, record the evaluated mask and exclusions, and report percentile, maximum, directionality, and peak-memory evidence.
- Treat visual fit, physical fit, and print success as unverified until directly observed.

## Boundaries
- Never overwrite or delete source scans or previously approved artifacts; work from copies and keep reversible checkpoints.
- Never bypass macOS security controls or install, uninstall, reset, or broadly reconfigure applications without explicit approval.
- Never substitute a mesh as the primary geometric source when the corresponding point cloud is available.
- Never reproduce scan noise when the requested result calls for symmetric, tangent, or otherwise regular design intent.
- Never use a global pass percentage as proof that each critical feature has the correct manufactured topology.
- Never purchase materials, start or monitor a physical print, or claim physical fit without observed evidence.
- Never publish private scans, drawings, videos, machine-specific paths, or user data in plugin artifacts or reports.

## Routes
- Select **Investigate** for analyze, assess, audit, diagnose, explain, inspect, investigate, review, or understand. Read [diagnose-and-verify.md](references/diagnose-and-verify.md).
- Select **Change** for add, align, build, change, compress, create, delete, edit, export, fix, implement, loft, optimise, optimize, rebuild, reconstruct, refactor, remove, repair, simplify, stitch, thicken, trace, turn, update, or write. Read [operate.md](references/operate.md).

## Operating rule

Read the selected route completely before acting. For live GUI work, use the host's computer-control capability when available and verify each material command from the application state. Prefer an equivalent bounded numerical or CAD-kernel route when it proves the required geometry without the GUI; if neither route is available, stop at a precise manual handoff rather than claiming completion.
