# Design

## Context

See `proposal.md` for motivation. Existing public documentation and tests already
define the release-candidate behavior; this change extracts only stable behavioral
contracts into a small capability taxonomy.

## Goals / Non-Goals

**Goals:**

- Make current externally visible behavior discoverable through OpenSpec.
- Preserve backend qualification boundaries and explicit-I/O semantics.
- Keep each requirement traceable to current documentation and tests.

**Non-Goals:**

- Redesign public interfaces or declare new support.
- Replace detailed guides, validation records, or the backend matrix.
- Import prospective MeldStore behavior into MeldDB's local specifications.

## Decisions

- Use five flat capabilities aligned with caller-visible concerns. A finer module-by-module taxonomy would mirror implementation rather than behavior.
- Capture the current baseline as ADDED requirements through the normal change lifecycle. Directly pre-populating main specs would bypass OpenSpec history.
- Keep scenarios representative rather than duplicating the full test suite. Existing tests remain the detailed executable evidence.

## Risks / Trade-offs

- **Baseline language can overstate behavior** -> Limit requirements to documented and tested contracts; preserve experimental labels.
- **Specs can drift from richer guides** -> Treat OpenSpec as the canonical behavioral summary and update it with future changes; retain guides for procedures and evidence.
- **Broad capabilities can hide edge cases** -> Link future deltas to the narrowest existing capability and split only when demonstrated work makes that useful.

## Migration Plan

Validate and archive this documentation-only change to create the five main specs.
No runtime migration or rollback is required; reverting the planning commit removes
the baseline without affecting data or code.
