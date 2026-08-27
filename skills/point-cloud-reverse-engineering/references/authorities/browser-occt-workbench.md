# Browser viewer and replayable OCCT route

Use this route when the declared authority is a replayable OpenCascade operation
chain controlled from a purpose-built browser workbench. The browser is the
interaction surface; authoritative geometry comes from clean replay, not from
page state, a WebGL mesh, or a screenshot.

Apply the [shared evidence and validation contract](../shared/evidence-and-validation.md).
If the authority has not been selected, return to
[stack-selection.md](../stack-selection.md) without constructing anything.

## Runtime boundary

1. Record whether OCCT runs as native server code, local desktop code, or WASM.
   Record exact application, kernel, serializer, and tessellator versions.
2. Keep the immutable full cloud in the evidence service or bounded numerical
   pipeline. Stream immutable point tiles and level-of-detail metadata to the
   browser; never silently promote visible tiles into the measurement set.
3. Set independent limits for tile cache, browser heap, kernel heap/process,
   fitting batches, workers, and threads. Eviction may remove display tiles but
   must not alter fixed validation masks.
4. Bind a local agent API to loopback unless the user has approved a protected
   remote deployment. Scope file access and operation mutation to the project.

## Operation-chain contract

Every accepted operation must serialize:

- stable operation ID, schema and operation version, type, typed parameters,
  input IDs, output IDs, and component frame;
- source and feature-contract hashes, units, source-to-authority transform, and
  authority/kernel version;
- raw fitted and regularised parameters, evidence mask, exclusions, uncertainty,
  tolerance, and the evidence-query result that accepted it;
- deterministic ordering and random seeds, or an explicit declaration that an
  operation is non-deterministic and therefore cannot be authority.

Do not store required geometry only in a JavaScript object, DOM node, browser
cache, transient selection, undo stack, or tessellated preview. Checkpoint the
chain after each accepted feature and keep the previous accepted checkpoint.

## Evidence and alignment stage

1. Fingerprint and preflight the source outside the browser heap. Verify units
   with an independent calibrated length before metric construction.
2. Display tile bounds, count, level, source checksum, and transform in the UI.
   Make display-only sampling unmistakable.
3. Create datum candidates from bounded source points, then record the accepted
   plane/axis/origin evidence and confidence in the contract.
4. Apply the explicit transform to named held-out datum points and verify its
   inverse, determinant, handedness, calibrated lengths, and post-transform
   bounds before allowing solid operations.

## Construction loop

1. Start with the smallest evidence-backed primitive chain. Prefer profiles,
   lines, arcs, extrusions, revolutions, analytic cuts, shared constraints, and
   instances for manufactured geometry.
2. Make crop, section, fit, sketch, Boolean, fillet, loft, stitch, pattern, and
   placement commands domain operations with typed inputs. Agent tools should
   call those operations and query evidence directly; pixel clicks are a
   recoverable fallback, not the durable interface.
3. Apply one feature-local mutation from the last accepted checkpoint. Rebuild
   downstream operations, query kernel facts, and compare the fixed local gate.
4. Reject and restore the previous chain when topology, an unrelated feature,
   uncertainty, or resource limits regress, even if the preview looks better.
5. Preserve separate components and construction geometry until their contracts
   pass. Union only when the requested deliverable requires it.

## Kernel canaries

Exercise small bounded canaries before relying on each advanced operation:

- a profile/extrude and cut with expected analytic plane/cylinder inventory;
- a tangent fillet with queried radius and continuity;
- a three-profile loft before guide rails, then a shared-seam two-patch stitch;
- a pattern containing an asymmetric instance so orientation errors are visible;
- STEP export/import with units, body count, bounds, volume, surfaces, and
  defining sections checked after reopen.

A failed canary disqualifies that operation/version combination. Do not repair a
kernel failure by substituting a visually similar preview mesh.

## Replay and validation

1. Close the browser and kernel session. Start an empty fresh process, load only
   the immutable source identity, validated contract, and serialized chain, then
   rebuild without cached B-rep or page state.
2. Compare operation and feature IDs, dependency graph, kernel facts, analytic
   surface inventory, bounds, volume, critical sections, and the fixed local and
   global evidence metrics.
3. Record deterministic B-rep identity when available; otherwise report exact
   facts plus tolerance-equivalent symmetric difference. Do not use equal
   preview meshes as proof of equal analytic geometry.
4. This fresh replay is a same-kernel Tier 1 check. Use an alternate importer for
   Tier 2 and a genuinely different CAD kernel for Tier 3 when available.
5. Apply the shared replayable OCCT completion gate. If STEP or STL is also
   requested, apply its additional authority/deliverable gate.

## Recovery and reporting

Autosave the chain and acceptance ledger atomically. After a browser, worker, or
kernel crash, reopen the last accepted checkpoint and replay it before proposing
another operation. Report the chain path/hash, clean-replay result, versions,
unit status, uncertainty, validation tier, export results, resource peaks, and
any browser-only state that still prevents authoritative regeneration.
