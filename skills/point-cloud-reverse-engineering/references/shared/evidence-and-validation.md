# Shared evidence and validation contract

Every modelling authority uses these gates. A host-specific playbook may add
checks, but it may not weaken them. Record observed facts, assumptions, and
unavailable checks separately; an unavailable check is not a pass.

## Evidence and authority gate

1. Preserve the original scan and fingerprint it once. Record format, fields,
   byte size, checksum, point count, bounds, and any scanner metadata.
2. Name the fixed **measurement evidence** independently from every crop,
   outlier-filtered set, registration subset, and display sample. Record the
   derivation, count, voxel or sampling rule, and checksum of each derivative.
3. Assign each input an evidence role. Point clouds and independently
   calibrated specifications may establish dimensions; photographs normally
   establish feature identity, topology, occlusion, and continuity only.
4. Declare the authority before construction: editable STEP/DWG, native
   `.blend`, replayable OCCT operation chain, or procedural mesh plus STL.
   Declare every requested derived artifact separately.
5. Record each critical feature's component, defining frame or section,
   primitive or mesh intent, G0/G1/G2 continuity where applicable, raw fit,
   regularised value, symmetry or repetition rule, evidence mask, exclusions,
   tolerance, and confidence.
6. Validate the machine-readable contract against
   [the JSON Schema](../../assets/feature-contract.schema.json) with
   [the validator](../../scripts/validate_feature_contract.py). Start from the
   [valid example](../../assets/contracts/feature-contract.valid.json); do not
   invent transform direction, matrix layout, units, or authority names.
7. Set point-batch, process-memory, and numerical-library thread limits before
   a large fit or distance run. The bundled
   [evidence CLI](../../scripts/point_cloud_evidence.py) is the deterministic
   preflight when its input format is supported.

The machine contract accepts XYZ-family text, PLY, E57, LAS, and LAZ evidence
artifacts so capable external routes can retain their native formats. The
bundled dependency-free CLI itself parses only strict headerless XYZ-style
text/CSV and ASCII PLY. Fingerprint any external conversion and declare it as a
separate derivative; never relabel an unsupported binary source as parsed.

Contract v1 covers exactly one independently accepted component. For an
assembly or scan containing separately modelled bodies, issue one contract per
component and aggregate their reported statuses outside the component
contracts. Do not call a component-global mask or result assembly-global.

## Unit-calibration gate

Do not infer millimetres merely because the object has plausible dimensions.

1. Record source units as `verified`, `provisional`, or `unknown`, plus the
   provenance of that status.
2. Verify scale with scanner metadata or at least one independent calibrated
   length that spans a useful fraction of the object. Prefer two non-collinear
   lengths or a calibrated artefact when anisotropic scale is plausible.
3. Record observed length, reference length, scale factor, uncertainty, and the
   exact transform in the feature contract. Recompute bounds and the calibration
   residual after applying it.
4. Verify axis order, handedness, transform direction, matrix layout, and
   determinant. Reject a reflection unless it is intentional and documented.
5. Repeat the calibrated-length and bounds check after every application or
   file-format handoff.

If scale remains provisional or unknown, construction may continue only as an
explicitly provisional experiment. Do not pass a metric tolerance, clearance,
manufacturing, or physical-fit gate.

## Metrology uncertainty budget

Keep residual error, evidence uncertainty, and manufacturing clearance as
different quantities. Before accepting a metric fit, estimate at least:

| Component | Evidence to record |
| --- | --- |
| `u_scan` | scanner calibration, repeatability, surface/material effects |
| `u_scale` | calibrated-length uncertainty and scale residual |
| `u_registration` | datum/ICP repeatability and held-out datum residuals |
| `u_sampling` | voxel/crop/normal sensitivity on a fixed validation set |
| `u_segmentation` | boundary-mask sensitivity for the critical feature |
| `u_model` | kernel/tessellation/query tolerance and fitting repeatability |

Use root-sum-square only for defensibly independent random components. Otherwise
report a conservative bound or interval and state the combination rule. Keep a
separate manufacturing allowance for process variation and desired physical
clearance; do not hide either inside the scan-to-model residual.

- Report residual statistics with the applicable uncertainty interval and only
  meaningful digits.
- If the declared tolerance is no larger than the evidence uncertainty, report
  the test as inconclusive rather than passed.
- Re-estimate affected components after a new registration, sample, surface
  treatment, or CAD-query backend.

## Alignment and handoff checks

1. Store one explicit source-to-authority 4x4 transform and its tested inverse.
   Apply both to held-out datum points; require round-trip error within the
   declared numerical tolerance.
2. Record the component frame, global frame, up axis, origin datum, matrix
   ordering, handedness, determinant, and units on both sides of each handoff.
3. Transform normals with the inverse-transpose of the linear transform and
   renormalise them. Do not use normal-angle metrics until normal orientation
   and reliability have been checked.
4. Recheck count, bounds, calibrated lengths, and named datum coordinates after
   import. Explain expected changes caused by cropping, filtering, or rotation.

## Global and feature-local metrics

Freeze validation masks before tuning the model. Use a fit subset and a distinct
fixed validation subset when point count permits.

For the contract component and every critical feature, record eligible and evaluated
count, coverage, P50/P95/P98/P99, mean, RMS, maximum, direction, exclusions,
batch size, thread cap, and peak memory. Every acceptance
result must own exactly one primary `global` or `critical-feature` mask. Record
global and critical-feature results separately in both required directions;
never combine masks in one result or cherry-pick a subset of eligible points.
An exclusion-free global result covers the complete direction query artifact.
A critical mask names the exact feature it validates and must have genuinely
different geometry from its component's global mask, not merely a different ID
or recomputed hash. Always report cloud-to-model and model-to-cloud separately:

Contract v1 uses exactly P50/P95/P98/P99 and the bundled linear percentile
convention: for sorted values, the zero-based position is
`(count - 1) * percentile / 100` and values between adjacent ranks are linearly
interpolated. External tools must export this convention or convert their
summaries before contract validation. Each distance result and each applicable
normal summary must include a `normalized-blocks-v1` certificate. Its contiguous
sorted blocks expose every interpolation endpoint and threshold transition, so
the validator can recompute count, mean, percentile, maximum, and threshold
facts, plus RMS for distance results, and reject combinations that no finite
sample can realize. The bundled
distance helper emits this certificate directly.

Certificate arithmetic uses finite IEEE-754 binary64 values with relative
comparison tolerance `1e-12` and zero absolute tolerance. It proves numerical
realizability within that declared envelope, not provenance from the named
artifact. Contract v1 accepts unsigned nonnegative distance magnitudes only;
do not present an uncertified signed bias as v1 acceptance evidence.

- **Cloud-to-model** measures agreement with observed evidence.
- **Model-to-cloud** measures unsupported or missing geometry only on surfaces
  that the scan could observe. Mask closure and occluded faces explicitly.

Use semantic checks in addition to nearest-distance statistics:

- fit planes, cylinders, cones, spheres, and tori on their declared masks and
  report parameter, axis, radius, and form residuals;
- compare reliable oriented normals on analytic fit surfaces, reporting angular
  P95 and the fraction exceeding the local limit;
- compare silhouettes or section contours in each feature's defining frame with
  bidirectional contour distance and Hausdorff maximum;
- report observed-surface coverage by spatial cells or area-normalised samples
  so dense flat regions cannot dominate sparse corners and openings;
- verify port/opening width, centre, axis, edge topology, and adjacent-wall
  thickness independently from the enclosure's global score;
- inspect every repeated instance's local transform and orientation.

A global pass never waives a failed topology, coverage, normal, or local-section
gate. A maximum driven by a documented outlier may be reported with and without
that exclusion, but the original result must remain visible.

Derive each result's `acceptance_status` from its recorded criteria and evidence;
do not copy a claimed status through unchecked. Contract validation and evidence
acceptance are separate states: `contract_valid` means the document is
structurally and semantically coherent, while `evidence_status` is `pass`,
`fail`, `inconclusive`, or `not-evaluated`. Report `ok` only when both contract
validity and an evidence pass are true. A helper operation can succeed while its
evidence remains `not-evaluated`; its `operation_ok` must not be presented as a
fit pass.

## Validation independence tiers

Name the strongest tier actually completed. Reopening is not automatically an
independent validation.

| Tier | Test | What it proves |
| --- | --- | --- |
| 0 | In-memory producer check | The current session can query its own result |
| 1 | Fresh process, same importer and kernel | Persistence and deterministic regeneration; not kernel independence |
| 2 | Alternate importer or implementation, possibly the same kernel family | File interoperability and a different import path; disclose shared kernel lineage |
| 3 | Cross-kernel or genuinely independent consumer | Strongest available evidence for topology and interchange |

At every completed tier, verify units, bounds, volume where applicable, body and
shell counts, validity, surface inventory, critical sections, and named feature
parameters. Do not describe Tier 1 as independent merely because it ran in a new
process. When Tier 3 is unavailable, state that limitation.

## Authority-specific completion gates

Apply the shared gates above, then exactly one primary authority gate. Apply
additional gates for every requested derived deliverable.

### Editable STEP or DWG authority

- Preserve the parametric source or editable drawing and record its feature
  graph, component identities, analytic surface classes, constraints, and units.
- Reopen the STEP/DWG at the strongest available validation tier. Confirm solid
  validity, body count, bounds, volume, surface inventory, radii, continuity,
  repeated-feature transforms, and defining sections.
- Regenerate any STL from the accepted B-rep. A mesh imported into CAD does not
  satisfy editable analytic STEP/DWG authority.

### Native BLEND authority

- Preserve native CAD Sketcher/Geometry Nodes objects, constraints, parameters,
  source/display collections, units, alignment, and contract identity.
- Save and reopen the `.blend` in a fresh Blender process. Use a read-only bridge
  inspection before further mutation and repeat an evaluated-copy geometry
  canary without destructively converting the native authority.
- Verify scene object/collection inventory, bounds, evaluated volume/topology,
  critical sections, and renderable evidence overlays. Do not claim STEP/DWG
  editability from a `.blend` or its evaluated mesh.

### Replayable OCCT authority

- Save a versioned, ordered operation chain with stable identifiers, typed
  parameters, dependencies, source/contract hashes, kernel version, and no
  hidden browser-only state.
- Rebuild from an empty state in a fresh process and compare operation count,
  named feature facts, B-rep hash or tolerance-equivalent geometry, sections,
  and fixed evidence metrics.
- Treat a browser preview as review evidence only. If STEP is requested, export
  it from the rebuilt chain and also pass the STEP/DWG gate.

### Procedural mesh and STL-only authority

- Preserve the procedural source, registration transform, masks, parameters,
  target thickness/offset, meshing resolution, and deterministic random seeds.
- Verify units, bounds, plausible volume, nonzero faces, winding, self-
  intersections, connected components, zero degenerate faces, and zero boundary
  and non-manifold edges unless the declared artifact intentionally remains open.
- Verify local fit on the fixed measurement evidence, wall thickness, clearances,
  and section contours. Label analytic editability, printability, and physical
  fit unverified unless separately tested.

## Completion report

Report source and derivative identities, authority, deliverables, unit status,
alignment, uncertainty budget, global and local metrics, validation tier,
authority-gate results, exclusions, resource use, and every unverified claim.
If any required gate fails, return the last accepted checkpoint and the smallest
next experiment instead of claiming completion.
