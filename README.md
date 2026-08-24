# Point Cloud Reverse Engineering

A Codex plugin for turning fused 3D-scan point clouds into verified CAD geometry with CrealityScan, CloudCompare, and BricsCAD. It covers physical-datum alignment, thin-crop section lofting, direct spline surface construction, fitted recesses, regularised design-intent geometry, reversible diagnosis, and evidence-gated DWG/STL exports.

The plugin contains instructions only. It does not bundle or install CrealityScan, CloudCompare, BricsCAD, scanner data, CAD drawings, or downloaded videos.

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

## Releases and updates

Every push to `main` cuts a semantic release. Commit subjects beginning with `feat` or containing `[minor]` produce a minor bump; `feat!`, `fix!`, or `BREAKING CHANGE` produce a major bump; everything else produces a patch. The release workflow updates both plugin manifests, creates a matching `vX.Y.Z` tag, and publishes a GitHub Release.

Refresh and reinstall the latest release with:

```bash
codex plugin marketplace upgrade point-cloud-reverse-engineering
codex plugin add point-cloud-reverse-engineering@point-cloud-reverse-engineering
```

Start a new Codex session after updating.

## Requirements and limits

- The relevant desktop applications must already be installed and licensed.
- Live application work requires a host with computer-control support; otherwise Codex gives a precise manual handoff.
- Source scans are preserved. Installs, resets, security changes, publishing, purchasing, and physical printing remain outside the skill's autonomous scope.
- Geometry and file checks do not prove physical fit. Use a fit coupon or observed trial before relying on a manufactured part.

## Packaging

This repository is dual-packaged: [`plugin.json`](plugin.json) supports Agent Plugins 1.0.0 clients, while [`.codex-plugin/plugin.json`](.codex-plugin/plugin.json) and [`.agents/plugins/marketplace.json`](.agents/plugins/marketplace.json) provide native Codex marketplace metadata.

The workflow is based on publicly demonstrated point-cloud reverse-engineering techniques from [Payo Tensile Creator](https://www.youtube.com/@Payo-TensileCreator), independently reproduced and converted into generic operating and verification rules. This project is not affiliated with or endorsed by the creator.
