# SirenGrid Phase 06 - AI Multimodal Intake and Fusion Design

## Authority and boundary

Phase 06 adds a control-room intake boundary for reports and supporting
evidence. AI interprets evidence; deterministic SirenGrid services and
operators remain authoritative for facts, activation, resources, routes,
coverage, hospitals, corridor actions, and driver alerts. A credible urgent
manual report may activate immediately without AI or corroboration.

The implementation reuses the Phase 03 `Report`, evidence metadata, incident,
timeline, and WebSocket structures. It does not create a second incident store,
citizen reporting application, embedding service, queue, background worker, or
autonomous action path.

## Locked provider policy

- Structured extraction primary/secondary: `NOT_SELECTED`; default disabled.
- Manual/operator structured intake: enabled and required fallback.
- ASR: Groq Whisper Large v3, Turbo fallback, then manual transcript.
- ASR and processing use one monotonic 30-second request budget.
- Vision: one fresh five-case safety benchmark before any opt-in provider;
  otherwise manual image evidence only; default remains disabled.

## Evidence claims

Each extracted field is an immutable claim with field, value, fact state,
report/evidence source, qualitative support (`LOW`, `MEDIUM`, `HIGH`),
provider/model metadata, observation time, provenance, and uncertainty. Claim
states are `ASSERTED`, `EXPLICIT_NEGATIVE`, and `UNKNOWN`; missing mention is
not a negative. Claims never directly mutate authoritative incident fields.

Material conflicts retain every claim and produce `CONFLICT`/
`REQUIRES_REVIEW`. Operator resolution is the only projection path and performs
one incident-version increment plus one append-only audit event.

## Media and provider boundary

Audio/image uploads are size- and MIME-bounded, stored outside SQLite under
opaque media IDs, and never expose local paths. Model output is untrusted JSON:
strict validation is required and structured output gets at most one repair
retry. Provider rate limits, outages, authentication failures, and malformed
results fail visibly without fabricated facts.

## Deterministic fusion

Fusion emits `AUTO_ASSOCIATE`, `SEPARATE_INCIDENT`, or `REQUIRES_REVIEW` using
trusted coordinates, 500 m/900 s prototype gates, known category compatibility,
contradiction checks, and at least one deterministic contextual match. No
embedding model/provider is used. Auto-association never delays initial
activation and never transfers committed operational state.

## Phase 06 API shape

REST remains canonical. The implementation extends `/api/v1/reports` and
`/api/v1/incidents` for intake, evidence/claim inspection, operator projection,
conflict resolution, and deterministic association review. WebSocket events are
only invalidation/update notifications. Raw evidence is append-only.
