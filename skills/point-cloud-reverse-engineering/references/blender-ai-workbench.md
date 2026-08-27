# Blender AI workbench route

Use this route when the user explicitly wants Blender, CAD Sketcher, Geometry
Nodes, or a Blender MCP/agent bridge. It is an AI-operated evidence and
modelling workbench; it becomes the production authority only when the declared
deliverable is the native `.blend` rather than editable STEP/DWG.

## Tool roles and compatibility

- Use Open3D or CloudCompare outside Blender for full-density alignment,
  segmentation, RANSAC/least-squares fitting, and bounded distance checks.
- Use Blender for scene organization, overlays, orthographic/section evidence,
  render capture, and isolated evaluation of the reconstruction.
- Use CAD Sketcher for native editable lines, arcs, constraints, and supported
  features such as extrude/revolve/array when those match the feature contract.
- Use a safety-aware local bridge such as Blender Agent Bridge when available.
  Require loopback binding, read-only inspection first, reversible previews or
  checkpoints for mutations, explicit trust for scripts, and project-scoped
  paths.
- Pin the exact Blender and extension releases. Verify their Blender/Python ABI
  compatibility before enabling them; do not assume an add-on archive that
  installs will also load.

Do not install or globally configure these tools without authorization. Do not
expose a Blender bridge on a non-loopback interface.

## Evidence and display split

1. Fingerprint the original point cloud and record format, fields, units,
   point count, bounds, normal quality, and checksum.
2. Align and fit against the fixed numerical evidence set. Keep thread counts,
   batches, masks, exclusions, and peak memory bounded and recorded.
3. Create a separately named voxel sample for interactive Blender display.
   Record its voxel size and point count as display-only metadata.
4. Import the display cloud without meshing it into the reconstruction. Put it
   in a source-evidence collection, mark it immutable with custom properties,
   and retain the source checksum and alignment transform on the scene.

Rendering millions of instanced point spheres can dominate memory and GPU time.
A smaller display sample is acceptable because measurements remain tied to the
separate numerical set.

## Native reconstruction

1. Create separate collections for source evidence, fitted datums,
   reconstruction, validation-only copies, and cameras/lights.
2. Set scene units explicitly and preserve the source-to-CAD transform.
3. Build the smallest CAD Sketcher primitive chain supported by the feature
   contract. Preserve raw fitted parameters and regularised dimensions as
   named properties or a sidecar contract.
4. Prefer normal UI/operator paths for interactive work. In deterministic
   headless work, use the extension's native data model only when documented or
   verified by a canary, preload only version-shipped assets required by its
   operator, and record the integration path. Do not patch extension source to
   hide an operator failure.
5. Keep separate components separate. Do not absorb a cable, connector, port,
   foot, or local recess into a convenient global enclosure fit.

## Agent operating loop

1. Start the local bridge explicitly and exercise a read-only tool such as
   scene-object listing or file diagnostics.
2. Record the baseline objects, collections, active authority, modifiers,
   parameters, and saved file path.
3. For a mutation, request or stage a reversible preview/checkpoint, apply one
   feature-local change, capture evidence, and compare the declared local gate.
4. Reject and revert a change that improves a global screenshot while damaging
   topology, an unrelated feature, or the production handoff contract.
5. Keep arbitrary Python or trusted-script execution explicit and scoped. A
   convenient bridge is not authority to run unreviewed scripts or access paths
   outside the project.

## Validation and reopen

- Capture isometric, orthographic, and defining-section overlays with source
  points and reconstruction visibly distinguishable.
- Evaluate the reconstruction as a mesh only on an isolated copy. New Curves
  plus Geometry Nodes objects may render while rejecting direct `to_mesh()`;
  duplicate the object/data and use evaluated object conversion instead.
- Check bounds, volume, nonzero topology, degenerate faces, boundary edges, and
  non-manifold edges on the isolated result.
- Save the native `.blend`, reopen it in a fresh Blender process, rerun a
  read-only agent inspection, and repeat the evaluation canary.
- Treat GPU-less EEVEE or Cycles stalls as renderer constraints, not geometry
  failures. A deterministic Workbench render is sufficient evidence when it
  exposes the required fit views.

## Production handoff

If STEP/DWG is required, stop treating Blender as the final authority after the
workbench passes. Export the machine-readable alignment and feature contract
defined in [stack-selection.md](stack-selection.md), regenerate the analytic
solid through OpenCascade/`$cad` or the chosen production CAD host, and run the
same local and global distance checks on that output. A mesh conversion from
the Blender preview is a derived visualization/print artifact, not a substitute
for analytic B-rep reconstruction.
