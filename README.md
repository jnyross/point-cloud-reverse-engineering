# Point Cloud Reverse Engineering

A Codex plugin for turning fused 3D-scan point clouds into verified CAD geometry. It supports the CrealityScan/CloudCompare/BricsCAD desktop workflow, an open-source Linux route using CloudCompare/Open3D plus cadgen/build123d/OpenCascade, a Blender/CAD Sketcher AI workbench, replayable browser/OCCT applications, and honest mesh-first routes for organic print-fit work. It covers physical-datum alignment, thin-crop section lofting, direct spline surface construction, fitted recesses, regularised design-intent geometry, reversible diagnosis, and evidence-gated STEP/DWG/BLEND/STL artifacts.

The plugin also bundles the complete `earthtojake/text-to-cad` skill suite and its runtime scripts. It does not install desktop applications, Python packages, printer software, scanner data, CAD drawings, or downloaded videos.

## Bundled skills

- `point-cloud-reverse-engineering` — reconstruct and verify design-intent CAD from scan evidence.
- `cad`, `cad-viewer`, `implicit-cad` — create, inspect, render, and review CAD models.
- `dfam-check`, `dxf`, `gcode`, `sendcutsend`, `bambu-labs` — validate and prepare manufacturing artifacts, with physical printer actions confirmation-gated.
- `step-parts` — find and verify standard purchasable STEP components.
- `sdf`, `srdf`, `urdf` — author and validate simulation and robot-description models.

The 12 companion skills are vendored from [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad). Each bundled skill retains its upstream provenance and licence file.

## Choose the authority, not just the application

The plugin separates four roles that are often forced into one tool:

- **Evidence engine:** CloudCompare or Open3D preserves, aligns, fits, and measures the point cloud.
- **Interactive workbench:** Blender, a tiled browser viewer, BricsCAD, or FreeCAD provides crops, sections, overlays, and review.
- **Modelling authority:** OpenCascade/build123d, BricsCAD, or another B-rep kernel owns editable manufacturing geometry when STEP/DWG is required.
- **Delivery validator:** an independent reader reopens the declared output and verifies analytic surfaces, bounds, topology, and any derived STL.

The recommended hybrid route uses Open3D/CloudCompare for evidence, a versioned feature-contract JSON for handoff, OpenCascade for production STEP, and Blender or a browser for AI-operated review. A display mesh or evaluated Blender object never silently replaces the production B-rep.

### Blender AI workbench

When Blender is requested, the skill can combine a pinned Blender release, CAD Sketcher, Geometry Nodes, Open3D, and a safety-aware localhost bridge such as Blender Agent Bridge. It keeps a bounded numerical measurement cloud separate from a smaller immutable display sample, builds the smallest native CAD Sketcher feature chain, captures overlay evidence, and reopens the `.blend` in a fresh process through a read-only bridge canary.

Blender is excellent for agent-operated exploration and visual review, but a `.blend` or evaluated mesh is not an editable STEP deliverable. When manufacturing CAD is required, the accepted alignment, raw fits, regularised parameters, feature topology, masks, and tolerances are handed to OpenCascade/`$cad` and revalidated against the same cloud evidence.

## Install in Codex

```bash
codex plugin marketplace add jnyross/point-cloud-reverse-engineering --ref main
codex plugin add point-cloud-reverse-engineering@point-cloud-reverse-engineering
```

Start a new Codex session after installation. Example requests:

- `Align this fused ASC point cloud in CloudCompare and export a verified LAS for BricsCAD.`
- `Trace splines on this point cloud, loft surface patches, stitch them, and thicken the quilt.`
- `Build a regularised holder recess from this scan and keep clearance as a calibration value.`
- `Diagnose this failed point-cloud handoff and recover the last verified state.`
- `Create an editable STEP model of this bracket and validate its exported STL.`
- `Reconstruct this scan as editable analytic STEP and STL on Linux using only open-source geometry tools.`
- `Use Blender, CAD Sketcher, Open3D, and a local agent bridge as an AI workbench, then regenerate the accepted result as verified OpenCascade STEP.`
- `Compare the Blender, browser/OCCT, BricsCAD, and organic mesh-first routes for this scan before choosing the modelling authority.`
- `Keep the full measurement cloud outside Blender, use a named display sample, and verify the saved scene through a read-only bridge tool.`
- `Check this mesh for additive-manufacturing problems and prepare a dry-run Bambu handoff.`

## Releases and updates

Every push to `main` cuts a semantic release. Commit subjects beginning with `feat` or containing `[minor]` produce a minor bump; `feat!`, `fix!`, or `BREAKING CHANGE` produce a major bump; everything else produces a patch. The release workflow updates both plugin manifests, creates a matching `vX.Y.Z` tag, and publishes a GitHub Release.

Refresh and reinstall the latest release with:

```bash
codex plugin marketplace upgrade point-cloud-reverse-engineering
codex plugin add point-cloud-reverse-engineering@point-cloud-reverse-engineering
```

Start a new Codex session after updating.

## Requirements and limits

- The selected route's tools must already be installed. The Linux route uses open-source CloudCompare/Open3D and an isolated Python 3.11/3.12 cadgen/build123d/OpenCascade runtime; proprietary desktop applications are optional.
- Blender, CAD Sketcher, and Blender agent bridges are optional external tools. Their exact releases and Python ABI compatibility must be pinned and canary-tested; this plugin does not install or expose them.
- A local Blender bridge must remain loopback-only, begin with read-only scene inspection, and use reversible previews/checkpoints for mutations. Configuring a client mid-session may require a new session.
- Individual companion skills may require the command-line tools or Python packages named in their own instructions.
- Live application work requires a host with computer-control support; otherwise Codex gives a precise manual handoff.
- Source scans are preserved. Installs, resets, security changes, publishing, purchasing, and physical printing remain outside the skill's autonomous scope.
- Geometry and file checks do not prove physical fit. Use a fit coupon or observed trial before relying on a manufactured part.

## Packaging

This repository is dual-packaged: [`plugin.json`](plugin.json) supports Agent Plugins 1.0.0 clients, while [`.codex-plugin/plugin.json`](.codex-plugin/plugin.json) and [`.agents/plugins/marketplace.json`](.agents/plugins/marketplace.json) provide native Codex marketplace metadata.

The workflow is based on publicly demonstrated point-cloud reverse-engineering techniques from [Payo Tensile Creator](https://www.youtube.com/@Payo-TensileCreator), independently reproduced and converted into generic operating and verification rules. This project is not affiliated with or endorsed by the creator.
