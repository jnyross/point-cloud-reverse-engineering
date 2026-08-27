# Linux open-source route

Read this route when the host is Linux, the user requests an open-source
toolchain, or the proprietary desktop applications in the main playbook are
unavailable.

## Tool mapping

- Use CloudCompare and/or Open3D for point-cloud import, inspection, cropping,
  datum alignment, subsampling, primitive fitting, and bounded distance fields.
- Use the bundled `$cad` workflow for editable analytic STEP construction.
  Its cadgen/build123d/OpenCascade stack preserves planes, cylinders, radii,
  tangency, patterns, named parameters, and feature intent.
- Derive STL from the accepted STEP and validate it with the bundled CAD and
  `dfam-check`/trimesh tools. Do not make a scan-following STL authoritative.
- FreeCAD, OpenSCAD, Blender, and MeshLab are optional. Install one only when a
  required operation is not already covered by CloudCompare/Open3D and `$cad`.
  When Blender is selected for AI-operated review, follow
  [blender-ai-workbench.md](authorities/blender-ai-workbench.md) while keeping `$cad`'s
  OpenCascade STEP as the production authority.

## Runtime

Prefer an isolated Python 3.11 or 3.12 environment or container over the host
Python. On an agent box configured with `cad-oss`, invoke the bundled CAD tools
through that runner, for example:

```bash
cad-oss /plugin/skills/cad/scripts/gen part.step.py --write
cad-oss /plugin/skills/cad/scripts/inspect validate part.step
cad-oss /plugin/skills/cad/scripts/export part.step --stl
cad-oss /plugin/skills/cad/scripts/snapshot --input part.step --output snapshots/part.png
```

Use the runner's mounted working directory for inputs and outputs. Do not copy
private scans into an image or repository. Keep numerical-library threads and
container memory bounded; record the actual cap and peak use with the fit
results.

## Workflow

1. Apply the [shared evidence and validation contract](shared/evidence-and-validation.md),
   including source fingerprint, unit calibration, transform checks, uncertainty
   budget, fixed validation masks, and feature-local acceptance before construction.
2. Import and align a reversible copy in CloudCompare. Verify entity type,
   units, point count, datum orientation, and bounds before and after export.
   A display is optional: use CloudCompare's command line for supported batch
   operations, and give a precise manual GUI handoff for an unsupported one.
3. Export the aligned cloud in a lossless supported point-cloud format. Do not
   convert it to a mesh merely to enter the CAD stage.
4. Build the smallest justified analytic feature program with `$cad`. Use
   shared profiles, symmetry, patterns, extrusions, revolutions, and analytic
   cuts; reserve splines for evidence-backed freeform regions.
5. Run CAD facts, surface-type, solid-validity, section, and snapshot checks.
   Run cloud-to-CAD and feature-local distances in bounded batches using the
   fixed alignment and masks.
6. Reopen the STEP in a fresh process and name it Tier 1 when it uses the same
   importer/kernel. Use an alternate importer or cross-kernel consumer for a
   stronger tier when available, then derive and structurally validate the STL.
   Report physical fit and printing as unverified until observed.
7. In a hybrid route, serialize the accepted alignment, feature topology,
   fitted and regularised parameters, masks, exclusions, and tolerances using
   the contract in [stack-selection.md](stack-selection.md). Regenerate the
   STEP from that contract and compare it against the same evidence used in
   the visual workbench.

Apply the shared editable STEP/DWG completion gate and every requested derived
artifact gate. The open-source route must meet the same evidence gates as the
desktop route. Tool substitution never relaxes topology, local-feature,
uncertainty, tolerance, independence, or resource-use requirements.
