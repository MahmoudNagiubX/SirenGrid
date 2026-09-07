# Phase 06 - TDD Implementation Plan

The plan is deliberately incremental and keeps every slice usable without AI
providers.

1. **Policy and artifacts:** record PD-028-PD-038, add the compact synthetic
   benchmark cases/results contract, constants, and the design boundary.
2. **Claims contract:** add strict fact-state/support schemas, provider-neutral
   adapter results, disabled structured-extraction state, and one-retry
   validation tests.
3. **Media and ASR:** add bounded opaque media storage/validation, audio intake,
   the approved ASR adapter chain under one deadline, and manual transcript
   fallback tests.
4. **Structured/image evidence:** add provider-neutral text/image processing,
   default-off provider configuration, fresh vision safety benchmark recording,
   and raw-evidence-preserving manual fallback.
5. **Claims and resolution:** persist immutable claims in existing report/
   evidence structures, expose conflict state, and add version-safe operator
   projection/resolution with one timeline event.
6. **Fusion:** implement deterministic duplicate association and review results,
   preserve report history, and add controlled duplicate-incident state/linking.
7. **API and live integration:** add minimal REST contracts, timeline events,
   WebSocket invalidation, and ensure manual activation/planning remain intact.
8. **Verification:** run focused tests, full Phase 01-05 regression, no-AI and
   bounded provider smokes where configured, audits, compile/lint, and publish
   `docs/PHASE_06_REVIEW.md`.

Every behavioral slice requires a failing test first where practical, a focused
green test, diff inspection, Ruff, and a clean commit before continuing.
