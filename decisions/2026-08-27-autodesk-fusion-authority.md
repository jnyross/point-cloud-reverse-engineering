# Autodesk Fusion native authority

date: 2026-08-27
status: implemented / locally validated
approval: user approved the specific Plugin Doctor plan through implementation, PR, merge, and release verification
rollback: tag `v0.6.0` (`49eec3f52ffc6c84ec0797892d830912601c9177`)

## Baseline

- Plugin Doctor profile: `router-plugin`
- deterministic errors: 0
- existing warnings: 2 deliberate packaging/size warnings
- existing proposals: 2 vendored-reference duplication proposals
- router fixtures: 39
- native Fusion authority: unavailable in the route matrix and feature contract

## Approved predicted delta

- Add Autodesk Fusion as an authority under the existing scoped Change route,
  not as a new permission-granting top-level route.
- Make native `.f3d` representable in the feature contract and require fresh
  source rebuild, zero warnings, output freshness, and edit/restore proof.
- Preserve the full-density point cloud as external measurement evidence and
  keep photos limited to topology, continuity, and appearance unless calibrated.
- Require fresh F3D reopen, independent STEP reopen, per-body STL validation,
  feature-local metrics, and standardized visual review.
- Keep Plugin Doctor at zero errors with no new warning or proposal.

## Plugin Doctor operation note

The suite's `add_playbook` operation adds a new top-level effectful route and a
generic edit stub. Fusion is a modelling authority selected inside the existing
Change dispatcher, so that operation would broaden mutation routing and omit
the required native-authority contract. The approved work is therefore a
scoped manual change measured against the immutable `v0.6.0` baseline.

## Actual delta

- One Fusion authority playbook now covers clean-room provenance, external
  evidence roles, scripted/native build freshness, flexible sweep checks,
  application-state recovery, F3D reopen/editability, STEP, per-body STL, and
  visual review.
- Contract v1 accepts `fusion_f3d` and requires B-rep facts plus a native Fusion
  gate containing fresh rebuild, edit/restore, output freshness, nonzero feature
  and body counts, and zero build warnings.
- Router fixtures increase from 39 to 43: direct Fusion construction, advisory
  selection, hybrid execution, and bare-authority non-mutation.
- Plugin Doctor remains at 0 errors with the same 2 warnings and 2 proposals.
- Repository validation, all 149 unit tests, schema self-tests, compatibility
  self-test, and deterministic core/full distribution checks pass.
