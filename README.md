# Point Cloud Reverse Engineering

A Codex plugin for turning fused 3D-scan point clouds into verified CAD geometry. It supports the CrealityScan/CloudCompare/BricsCAD desktop workflow and an open-source Linux route using CloudCompare plus cadgen/build123d/OpenCascade. It covers physical-datum alignment, thin-crop section lofting, direct spline surface construction, fitted recesses, regularised design-intent geometry, reversible diagnosis, and evidence-gated STEP/DWG/STL exports.

The plugin also bundles the complete `earthtojake/text-to-cad` skill suite and its runtime scripts. It does not install desktop applications, Python packages, printer software, scanner data, CAD drawings, or downloaded videos.

## Bundled skills

- `point-cloud-reverse-engineering` — reconstruct and verify design-intent CAD from scan evidence.
- `cad`, `cad-viewer`, `implicit-cad` — create, inspect, render, and review CAD models.
- `dfam-check`, `dxf`, `gcode`, `sendcutsend`, `bambu-labs` — validate and prepare manufacturing artifacts, with physical printer actions confirmation-gated.
- `step-parts` — find and verify standard purchasable STEP components.
- `sdf`, `srdf`, `urdf` — author and validate simulation and robot-description models.

The 12 companion skills are vendored from [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad). Each bundled skill retains its upstream provenance and licence file.

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

- The selected route's tools must already be installed. The Linux route uses open-source CloudCompare and an isolated Python 3.11/3.12 cadgen/build123d/OpenCascade runtime; proprietary desktop applications are optional.
- Individual companion skills may require the command-line tools or Python packages named in their own instructions.
- Live application work requires a host with computer-control support; otherwise Codex gives a precise manual handoff.
- Source scans are preserved. Installs, resets, security changes, publishing, purchasing, and physical printing remain outside the skill's autonomous scope.
- Geometry and file checks do not prove physical fit. Use a fit coupon or observed trial before relying on a manufactured part.

## Packaging

This repository is dual-packaged: [`plugin.json`](plugin.json) supports Agent Plugins 1.0.0 clients, while [`.codex-plugin/plugin.json`](.codex-plugin/plugin.json) and [`.agents/plugins/marketplace.json`](.agents/plugins/marketplace.json) provide native Codex marketplace metadata.

The workflow is based on publicly demonstrated point-cloud reverse-engineering techniques from [Payo Tensile Creator](https://www.youtube.com/@Payo-TensileCreator), independently reproduced and converted into generic operating and verification rules. This project is not affiliated with or endorsed by the creator.
