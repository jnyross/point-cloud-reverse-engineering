---
name: point-cloud-reverse-engineering
description: Turns fused 3D-scan point clouds into verified, design-intent CAD geometry for people doing practical reverse engineering in CrealityScan, CloudCompare, and BricsCAD, with reversible recovery and evidence-gated exports.
---

# Point Cloud Reverse Engineering

## Trigger
- Turn this fused CrealityScan point cloud into an aligned BricsCAD model and verify the exported STL.
- Align this ASC point cloud in CloudCompare with the sole down and export a BricsCAD-compatible LAS.
- Trace splines directly on this point cloud, loft the surface patches, stitch them, and thicken the result.
- Build a fitted holder with a recessed seat from this scanned object while preserving the source scan.
- Diagnose why this CloudCompare or BricsCAD point-cloud workflow failed, reverse ineffective changes, and recover the last verified state.

## Non-triggers
- Repair or slice this STL mesh without using a point cloud.
- Create an ordinary CAD part that has no scan or point-cloud evidence.
- Summarize these YouTube videos without applying the demonstrated reverse-engineering workflow.
- Recommend a scanner, printer, or CAD package to buy.
- Start, monitor, or operate a physical 3D print.

## Inputs
A fused point cloud in ASC, E57, or LAS form, raw or already aligned; the user must also state the object or design intent and any fit, clearance, symmetry, or regularity requirements. A mesh may be secondary evidence but is not the primary source when a point cloud is available.

## Mutation policy
scoped: only requested surface.

## Verification
- Identify whether every source is a point cloud or mesh and preserve the original source unchanged.
- Verify units, scale, orientation, point count, and bounding dimensions after each application handoff.
- Verify both feature topology and database state: confirm each intended sharp, rounded, tangent, or chamfered transition in orthographic or section views, then confirm the intended entity types and counts.
- Save the DWG to the stated path, confirm it reopens, and confirm no uncommitted drawing changes remain before completion.
- For STL output, verify plausible dimensions and volume, nonzero triangle count, zero degenerate triangles, zero boundary and non-manifold edges, and consistent winding.
- Treat visual fit, physical fit, and print success as unverified until directly observed.

## Boundaries
- Never overwrite or delete source scans or previously approved artifacts; work from copies and keep reversible checkpoints.
- Never bypass macOS security controls or install, uninstall, reset, or broadly reconfigure applications without explicit approval.
- Never substitute a mesh as the primary geometric source when the corresponding point cloud is available.
- Never reproduce scan noise when the requested result calls for symmetric, tangent, or otherwise regular design intent.
- Never purchase materials, start or monitor a physical print, or claim physical fit without observed evidence.
- Never publish private scans, drawings, videos, machine-specific paths, or user data in plugin artifacts or reports.

## Routes
- Select **Investigate** for analyze, assess, audit, diagnose, explain, inspect, investigate, review, or understand. Read [diagnose-and-verify.md](references/diagnose-and-verify.md).
- Select **Change** for add, align, build, change, create, delete, edit, export, fix, implement, loft, reconstruct, refactor, remove, repair, stitch, thicken, trace, turn, update, or write. Read [operate.md](references/operate.md).

## Operating rule

Read the selected route completely before acting. For live GUI work, use the host's computer-control capability when available and verify each material command from the application state. If the required application cannot be controlled, stop at a precise manual handoff rather than claiming completion.
