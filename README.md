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

### Executable evidence contract

The point-cloud skill now includes a Draft 2020-12 feature-contract schema, a dependency-free semantic validator, and bounded deterministic point-cloud canaries. The contract records source and derivative identities, calibrated units, explicit row-major transforms, modelling authority, component intent, raw and regularised parameters, masks, uncertainty, semantic checks, coverage, validation tier, and deliverable gates. Contract v1 accepts exactly one independently validated component; assemblies use one contract per component so a component-global score cannot masquerade as assembly-wide coverage. Every acceptance result owns exactly one global or critical-feature mask; global and local results are separate in both directions, evaluate every eligible point, and gate exactly P50/P95/P98/P99 plus maximum, coverage, uncertainty, and any applicable normal checks. A critical mask must identify the exact feature and have a distinct canonical definition from its component's global mask.

Every distance result and every applicable normal summary carries a compact `normalized-blocks-v1` realizability certificate. The validator recomputes threshold count, mean, percentile, and maximum facts—plus RMS for distance results—from contiguous sorted blocks and rejects impossible combinations; the evidence helper emits the same certificate from its measured distances. These checks use the schema's documented finite binary64 comparison envelope (relative tolerance `1e-12`, zero absolute tolerance). They prove numerical realizability, not that a self-attested certificate came from the named source artifact. Contract v1 therefore accepts unsigned distance magnitudes only; signed-bias certification remains outside v1.

```bash
python3 skills/point-cloud-reverse-engineering/scripts/validate_feature_contract.py \
  skills/point-cloud-reverse-engineering/assets/feature-contract.example.json --pretty

python3 skills/point-cloud-reverse-engineering/scripts/point_cloud_evidence.py \
  --pretty fingerprint scan.xyz

python3 skills/point-cloud-reverse-engineering/scripts/point_cloud_evidence.py \
  --pretty sample scan.xyz --role measurement --count 2000 --frame scan-mm \
  --output measurement.xyz

python3 skills/point-cloud-reverse-engineering/scripts/point_cloud_evidence.py \
  --pretty distance measurement.xyz model-sample.xyz --frame cad-mm \
  --tolerance 0.20 --max-a 2000 --max-b 2000
```

Validator output separates `contract_valid` from the derived `evidence_status` (`pass`, `fail`, `inconclusive`, or `not-evaluated`); `ok` is true only when the contract is valid and its required evidence passes. Evidence-helper output instead uses `operation_ok` to report successful execution. Fingerprint, sample, and raw distance operations remain `not-evaluated` until their measurements are placed under explicit acceptance criteria, while the transform canary can directly pass or fail its declared numerical gates.

The bundled distance command is deliberately a bounded point-to-point canary. It accepts strict headerless XYZ-style text/CSV and ASCII PLY, and does not replace feature-local point-to-B-rep queries, semantic surface checks, section comparisons, coverage analysis, or uncertainty accounting in the selected modelling authority. E57, LAS, and LAZ remain supported evidence formats in the contract and external CloudCompare/Open3D routes; they require a capable external reader or an explicitly fingerprinted conversion before using the bundled canary.

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

Every non-bot push to `main` cuts a semantic release after the repository quality gate passes. A Conventional Commit `feat` header or `[minor]` marker produces a minor bump; any valid Conventional Commit header containing `!`, or a `BREAKING CHANGE`/`BREAKING-CHANGE` footer, produces a major bump; everything else produces a patch. The workflow updates both versioned plugin manifests, atomically pushes a matching `vX.Y.Z` tag with the release commit, and publishes a GitHub Release with checksums plus two fixed-builder-deterministic, source-map-free archives:

- `core` contains the reverse-engineering, STEP-first CAD, and CAD review skills.
- `full` preserves all 13 existing reverse-engineering, manufacturing, printing, catalog, and robotics skills.

Refresh and reinstall the latest release with:

```bash
codex plugin marketplace upgrade point-cloud-reverse-engineering
codex plugin add point-cloud-reverse-engineering@point-cloud-reverse-engineering
```

Start a new Codex session after updating.

## Compatibility and repository checks

[`compatibility.json`](compatibility.json) separates tested tuples, probe-only observations, concrete incompatibilities, and unknowns. By default the preflight reads filesystem and package metadata without launching discovered Blender, CloudCompare, bridge, or CAD runtimes:

```bash
python3 scripts/compatibility_preflight.py
python3 scripts/compatibility_preflight.py --strict-route open-source-brep
python3 scripts/compatibility_preflight.py --probe-executables
```

`--probe-executables` is an explicit opt-in to bounded background/version/import probes. It never connects an agent bridge or opens geometry, but third-party tools may perform their own cache or configuration initialization. Strict mode passes only when every required component matches recorded compatibility evidence and the integrated route itself is recorded as tested. An installed Blender extension manifest alone remains unverified because it does not prove that the extension is enabled or loadable. Use `--allow-unverified` only when a fully identified probe-only route is acceptable; unknown is never treated as verified.

Before proposing a release, run the same dependency-free behavior gate and deterministic canaries used by CI:

```bash
python3 scripts/validate_repo.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/build_distributions.py --check
```

[`vendor-lock.json`](vendor-lock.json) records byte-for-byte provenance for the 12 companion skill trees. [`distribution.json`](distribution.json) defines the two release profiles; configured paths and repository symlinks are rejected by the builder rather than followed into an archive.

## Requirements and limits

- The selected route's tools must already be installed. The Linux route uses open-source CloudCompare/Open3D and an isolated Python 3.11/3.12 cadgen/build123d/OpenCascade runtime; proprietary desktop applications are optional.
- Blender, CAD Sketcher, and Blender agent bridges are optional external tools. Their exact releases and Python ABI compatibility must be pinned and canary-tested; this plugin does not install or expose them.
- A local Blender bridge must remain loopback-only, begin with read-only scene inspection, and use reversible previews/checkpoints for mutations. Configuring a client mid-session may require a new session.
- Individual companion skills may require the command-line tools or Python packages named in their own instructions.
- Live application work requires a host with computer-control support; otherwise Codex gives a precise manual handoff.
- Source scans are preserved. Installs, resets, security changes, publishing, purchasing, and physical printing remain outside the skill's autonomous scope.
- Geometry and file checks do not prove physical fit. Use a fit coupon or observed trial before relying on a manufactured part.

## Packaging

This repository is dual-packaged: [`plugin.json`](plugin.json) supports Agent Plugins 1.0.0 clients, while [`.codex-plugin/plugin.json`](.codex-plugin/plugin.json) and [`.agents/plugins/marketplace.json`](.agents/plugins/marketplace.json) provide native Codex marketplace metadata. Pull requests run the repository-owned quality workflow, while pushes to `main` run the same gate before release preparation. A scheduled compatibility workflow publishes a metadata-only, machine-neutral preflight report.

The workflow is based on publicly demonstrated point-cloud reverse-engineering techniques from [Payo Tensile Creator](https://www.youtube.com/@Payo-TensileCreator), independently reproduced and converted into generic operating and verification rules. This project is not affiliated with or endorsed by the creator.
