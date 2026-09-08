# Capture to verified measurement cloud

- [Scope and default](#scope-and-default)
- [Preserve and identify inputs](#preserve-and-identify-inputs)
- [Extract and import scans](#get-scans-out-of-crealityscan-and-into-cloudcompare)
- [Segment and register](#segment-and-register-multiple-passes)
- [Verification and comparisons](#verification-and-fair-comparisons)
- [Compact CAD handoff](#handoff-to-compact-cad)
- [macOS and UI recovery](#macos-and-native-ui-recovery)

## Scope and default

For agent-operated reverse engineering, default to **CrealityScan capture/export
-> CloudCompare cleanup, rigid alignment and measurement -> compact parametric
CAD**. Existing usable per-pass clouds do not require another native fusion.
Use vendor fusion when capture recovery or a controlled comparison demonstrates
a relevant benefit. More vertices or smoother surfaces alone do not establish
better dimensional accuracy. Honour an explicit request to use or compare both
applications, and label each completed stage by the application that did it.

Preparation-only requests end at a verified cloud; they do not require a CAD
authority or feature contract. Establish object scope, units, source identity,
datums, retained regions and requested output. Before subsequent construction,
return to the authority dispatcher and its full shared evidence contract.

## Preserve and identify inputs

1. Inventory sessions and outputs before mutation. Back up the complete vendor
   project before native processing; verify file counts, sizes and hashes.
   Keep immutable source clouds and separately named working copies.
2. Use targeted project metadata and allowlisted path fields to locate files.
   Do not dump application preferences or whole logs: they can contain account
   tokens. Keep private paths, scans and screenshots out of public plugins.
3. Inspect format headers, properties, counts, coordinate bounds and units.
   Distinguish raw acquisition frames, per-pass registered clouds, fused clouds,
   meshes and mesh vertices. In one observed CrealityScan layout,
   `session/result/model.ply` was the existing per-pass cloud and `Fused.ply`
   was a mesh. Verify each project; names alone do not prove semantics. Preserve
   the project-to-session mapping rather than guessing from directory order.
4. Accept PLY or a supported point-cloud export; ASC is not mandatory. Inspect
   ASCII delimiters, headers and column meanings before mapping XYZ, normals,
   intensity or colour. Never assume six columns mean XYZ plus normals. For
   binary PLY, use declared types and byte order. Mesh vertices are reconstructed
   samples, not recovered original measurements.
5. Record source hashes, units and calibration evidence, scanner/app versions
   and processing settings. Provisional units permit explicitly labelled
   diagnostics, not dimensional or fit claims.

## Get scans out of CrealityScan and into CloudCompare

**Normal export:** open the intended saved project, select the required scan or
processed result, and use the available export control to write a **point
cloud** (PLY or ASC when offered) to a separate working folder. Inspect the
actual export options; labels and availability depend on version and processing
state. Export passes individually when registration is the next step, and name
each copy unambiguously. If the UI requires fusion before export, the project
file route below may provide an already usable per-pass cloud. Do not export STL
and describe it as the original cloud.

**Existing project files (verified macOS route):**

1. Save the project and wait for writes to finish. Locate its folder through the
   app's project location or Finder. The observed macOS location was
   `~/Library/CrealityScan/Projects/<project>/`; use Finder **Go to Folder** for
   the hidden Library. This is a version-specific lead, not a universal path.
2. Back up the whole project and verify it before native mutations. Work from
   that stable copy. Read `project.obp` narrowly: its `sessions` list identifies
   the opaque session directories, while `data_dir` identifies project data.
   Do not mistake every subdirectory for a scan. Preserve session IDs/order in
   a manifest and confirm their correspondence to visible scan names before
   assigning friendly names; do not rely on alphabetical directory order.
3. For each listed session, inspect `<session-id>/result/model.ply`. In the
   verified project these were directly readable per-pass point clouds, so no
   additional CrealityScan fusion or GUI export was needed. Copy them to the
   working folder as separately named PLYs and verify source/copy SHA-256, count
   and header. Do not edit the project-owned files. If absent or unreadable,
   inspect the actual saved state and use native export; do not guess a binary
   decoder for acquisition databases such as `resources.obscan`.
4. If evaluating native fusion, copy `result/Fused.ply` separately after
   completion and stable writes. Inspect vertex **and face** elements: a mesh
   loaded as a mesh or reduced to its vertices must remain labelled as such.
   Never silently substitute it for the corresponding `model.ply` cloud.
5. Open the working PLY through CloudCompare's file-open control or supported
   CLI `-O` input. Check the DB-tree entity type, point count, fields, bounding
   dimensions and source identity before processing. For ASC, inspect the text
   first and map columns explicitly in the import dialog. Accept no unexplained
   scale or coordinate shift; record any global shift and reverse it on export
   when required by the chosen coordinate convention.
6. Load each pass separately, give entities distinguishable names/colours, and
   inspect before combining. Save processed output to a new path, reopen it,
   and compare counts/bounds with the logged result. Opening a file proves
   import, not successful support removal, registration or fusion.

## Segment and register multiple passes

1. Review each pass independently in orthographic views and defining sections.
   Separate the table, temporary support and object. Confirm ambiguous support
   boundaries with the user when they change the retained geometry. A large
   plane may be the table, not the object's face; a fit stuck at its parameter
   bounds is a warning to inspect the mask/model.
2. Preserve masks and point indices for every crop and filter, with before/after
   counts. Protect rims, mating faces and small features. Quarantine an
   inconsistent pass with evidence and reason rather than forcing it into a
   merge. Do not invent unobserved surfaces or silently fill holes.
3. Establish coarse orientation from physical datums and plausible geometry,
   then use fixed-scale rigid registration. Record source/reference roles,
   matrices, coordinate convention, transform order and inverses; verify a
   proper rotation, handedness and independently calibrated lengths.
4. Register same-face passes first. For front/back captures of a thin disc or
   similar part, use genuinely shared geometry such as the cylindrical rim for
   cross-face ICP. Unconstrained face-to-face ICP can collapse opposite planes
   and destroy thickness while reporting a small residual. Inspect axial
   sections and face separation after registration. A narrow or featureless rim
   can itself underconstrain alignment: use datums and report ambiguity.
5. Rotational symmetry may leave yaw or thread phase unobservable. Do not report
   such a transform component as measured merely because ICP chose a value.
6. Choose outlier filters, overlap and sample spacing from capture quality and
   feature scale. SOR with 20 neighbours/2 sigma, 95% same-face overlap, 85%
   shared-rim overlap and 0.15 mm spatial sampling were useful in one small-part
   experiment; these are starting points to validate, not defaults for other
   scans. Crop dimensions must be fitted to the current object.
7. Merge accepted transformed passes, then spatially subsample if needed. Keep
   a pass-coloured diagnostic and unsampled accepted evidence. State whether
   the method selects measured points, averages them or reconstructs samples.

## Verification and fair comparisons

- Reopen each final file and check finite coordinates, count, bounds, units,
  retained/excluded regions and requested spacing. If claiming measured-point
  preservation, verify output membership against the transformed source points
  within a stated numerical tolerance. Do not make that claim for fusion or
  voxel averages. Verify minimum separation when promising minimum spacing;
  a voxel size alone is not that guarantee.
- Keep command logs, masks, settings, transforms and source hashes sufficient
  to reproduce the accepted result. Report trimmed ICP RMS **and** untrimmed
  median/P95 distances, directions, regions and coverage. Nearest-neighbour
  distances depend on sample density and direction; they are not absolute
  accuracy. Use the full shared percentile profile for later CAD validation.
- Compare methods using the same source passes, retained physical regions,
  sampling procedure, datums and alignment protocol. Equal nominal spacing
  need not yield equal point counts. Keep whole-dataset and matched-subset
  comparisons separate. Do not add an unreported cross-method ICP that hides
  offsets or changes in the reconstructed geometry.
- Compare planes, diameters, face separation, rim/edge sections and small
  retained features. Separate noise reduction from systematic displacement.
  Independent physical measurements are needed to decide dimensional accuracy.
- Call vendor-fused samples subsequently cropped/aligned in CloudCompare a
  **hybrid** result. Do not claim an entirely native pipeline unless native
  cleanup, registration, export and read-back were actually completed. Pending
  UI actions and successful fusion of individual passes are partial evidence.
- Deliver the accepted cloud plus a concise manifest/report containing source
  identities, retained passes, exclusions, transforms, settings, metrics,
  section views and unresolved uncertainty. A ZIP should be read back and its
  members verified before handoff.

## Handoff to compact CAD

Fit the fewest evidence-backed planes, cylinders, lines/arcs and revolved
profiles that preserve meaningful sections and features. A stud does not prove
thread pitch, internal construction or unseen geometry; obtain dimensional
evidence before adding them. Keep local uncertainty explicit, and separate raw
fit, design regularisation and manufacturing clearance. A cleaned cloud or
locally valid STEP does not prove native CAD save/editability or physical fit.

For desktop handoff, align from manufactured datums, inspect top/front/side and
isometric views, and recheck explainable counts and bounds. For a hand plane,
the sole can define XY and heel-to-toe X, with side planes disambiguating width.
Keep an E57 archive when useful and export LAS for the existing BricsCAD route;
verify the actual destination import instead of inferring success from export.

## macOS and native UI recovery

Prefer a supported CLI/API for repeated processing. Read bundle metadata and
the [compatibility preflight](../../../scripts/compatibility_preflight.py)
before optional executable probes. Even help/version commands can initialize
GUI libraries; a successful probe is not processing proof.

An observed macOS CloudCompare 2.13.2 Cocoa bundle aborted with pasteboard/
HiServices XPC errors (exit 134) in a restricted launch. An `offscreen` retry
also failed where only Cocoa was bundled. In that environment, the approved
native Cocoa CLI launch outside the restricted sandbox completed processing.
Treat this as a conditional recovery lead: inspect the actual error and use
the platform's approval mechanism for a bounded native launch when required.
Do not blindly repeat the failing route, assume offscreen support, disable
security globally or alter Qt installations. Verify output files and logs.

For native custom controls, verify the effect of each action from application
state, not from a tool's successful click return. Working screenshots or keys
do not prove pointer support. A tiny drag that worked once is not a repeatable
automation method. Bound troubleshooting attempts and preserve the checkpoint.

Global synthetic mouse input can interrupt the user. Use only the currently
authorized input route. PID-targeted events and private event sources do not
prove background operation: an observed targeted mouse move changed cursor or
foreground state before its intended click. Check cursor and foreground state
around a bounded probe; stop immediately on unwanted changes. When the user
requires non-disruptive operation, do not resume a global fallback. Disable
abandoned helpers, continue through CLI where possible, or report the exact
remaining native step. A suspected custom input-backend cause remains a
hypothesis until demonstrated.
