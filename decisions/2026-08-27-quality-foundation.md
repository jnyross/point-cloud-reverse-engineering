# Reverse-engineering quality foundation

date: 2026-08-27
status: implemented / validated
approval: user approved the ranked Plugin Doctor plan and requested implementation and merge
rollback: tag `v0.5.0` (`e679cb7b584a964c1b24954ab00495c95bd5907e`)

## Baseline

- Plugin Doctor profile: `router-plugin`
- deterministic errors: 0
- skills: 13
- references: 47
- routes: 5
- router fixtures: 19
- existing warnings: 2 deliberate packaging/size warnings
- existing proposals: 2 context-local repeated CLI examples
- point-cloud core tooling: prose only; no schema, validator, or synthetic numerical canary
- release workflow: manifest/release checks only; no repository behavior gate
- release skill payload: 34.75 MiB raw; 17 source maps use 12.34 MiB

## Approved operations and predicted deltas

1. Add a versioned feature-contract schema, semantic validator, deterministic
   evidence helpers, and synthetic fixtures.
   - Predicted: reproducible transform, sampling, mask, uncertainty, and
     authority handoffs; fewer per-job bespoke implementations.
2. Refactor intent and authority routing while preserving every existing
   desktop, Linux/OpenCascade, Blender, and scan-following method.
   - Predicted: comparison/selection requests remain read-only; direct
     browser/OCCT and organic mesh-first jobs reach dedicated playbooks.
3. Replace unconditional STEP/DWG completion with shared evidence gates and
   authority-specific completion branches.
   - Predicted: valid BLEND, replayable OCCT, and STL-only jobs can complete
     honestly without weakening B-rep requirements when STEP/DWG is declared.
4. Add metrology uncertainty, semantic-surface validation, coverage, normal,
   section, and validation-tier rules.
   - Predicted: fewer false passes from global or nearest-face distance scores.
5. Add repository-owned behavioral validation and make release fail closed.
   - Predicted: broken manifests, links, routes, contracts, vendor parity, or
     synthetic evidence checks block release before versioning.
6. Split shared evidence guidance from host-specific desktop instructions.
   - Predicted: approximately 1,600 fewer irrelevant tokens on Blender routes.
7. Lock vendored provenance and tested compatibility; fix breaking-footer
   detection; publish source-map-free core and full release artifacts.
   - Predicted: exact upstream parity is machine-verifiable and compressed
     production downloads fall by about 31% without removing old methods.

## Plugin Doctor operation note

The suite's built-in `add_playbook` operation emits generic edit stubs, and
`split_skill` only splits a whole `SKILL.md` into another skill. Neither can
express the approved domain-specific references, two-stage authority routing,
schema/tooling, or shared-reference extraction safely. The implementation is
therefore scoped manual work, measured against this baseline and the immutable
`v0.5.0` rollback point.

## Actual delta

- Plugin Doctor remains at 0 deterministic errors with all 13 skills present.
  Routing is reduced from 5 routes to 4 and its executable fixture set grows
  from 19 to 39 cases. References move from 47 to 46; the same 2 deliberate
  warnings and 2 vendored-reference proposals remain.
- Every legacy desktop, Linux/OpenCascade, Blender, scan-following, mesh-first,
  manufacturing, printing, catalog, and robotics method remains available.
  The full profile contains all 13 skills; the core profile contains the point-
  cloud, STEP-first CAD, and CAD-viewer skills.
- Contract v1 now covers exactly one independently accepted component and a
  fixed P50/P95/P98/P99 profile for each global/critical result and direction. Each
  result, and every applicable normal summary, carries a bounded normalized-
  block realizability certificate. The validator proves the declared count,
  threshold split, percentile, mean, maximum, and distance RMS can coexist
  within the documented binary64 comparison envelope.
- The bundled evidence CLI has strict XYZ/CSV and ASCII PLY parsers, stable
  distance arithmetic, bounded stdlib/SciPy backends, deterministic role-
  separated sampling, pinned source descriptors, and descriptor-relative
  atomic publication. External E57/LAS/LAZ evidence remains an explicit
  CloudCompare/Open3D responsibility.
- The frozen tree passes 147 tests on Python 3.14 and Python 3.11 (2 expected
  optional-jsonschema skips on the latter), repository validation, formal
  schema parity where installed, Plugin Doctor gates, all 13 skill validators,
  release/preflight self-tests, and byte-for-byte distribution checks.
- `operate.md` falls from 2,109 to 1,661 words (21%). More importantly, Blender,
  browser/OCCT, and mesh-first jobs no longer load the unrelated desktop
  playbook. The predicted 1,600-token Blender reduction was not claimed: the
  expanded shared evidence contract is intentionally still loaded.
- Release payloads exclude 17 source maps that occupied 12.34 MiB raw. The
  current deterministic archives are approximately 2.9 MiB (`core`) and
  6.9 MiB (`full`); v0.5.0 had no release assets. CI now gates pull requests on
  Python 3.11/3.13, while the release workflow separates read-only preparation
  from a minimal write job and publishes matching checksums atomically.

## Deliberate v2 residuals

- A realizability certificate proves numerical consistency, not that its
  self-attested measurements came from the named source artifact. Stronger
  provenance would require authority-produced evidence files or attestations.
- Composite mask geometry, parameter-to-feature threshold lineage, uncertainty
  confidence-factor semantics, and section/normal source-artifact provenance
  can be represented more explicitly in a future contract revision.
- Contract v1 accepts unsigned distance magnitudes only. Signed-bias acceptance
  needs a sign-assignment certificate and is rejected rather than guessed.
- Physical fit, print success, and manufacturing certification remain observed
  external outcomes, not conclusions of the numerical validator.
