# Phase 06 benchmark inputs

These cases are synthetic/team-created fixtures for the compact Phase 06
provider and fusion benchmark. They contain no real emergency caller data or
private personal information and are not operational truth.

The set deliberately covers Egyptian Arabic, English, mixed-language text,
unknown facts, explicit and conflicting casualty claims, ambiguous location
phrases, schema/authority safety checks, and related versus unrelated report
pairs. Provider responses are not stored here. Benchmark summaries store only
metrics and safe status/error categories.

Structured extraction remains `NOT_SELECTED` and default-disabled under PD-028.
Vision remains default-disabled under PD-029. The fresh benchmark uses five
bounded safety assertions over the authorized synthetic Phase 00 fixture; it
does not imply that vision is operationally enabled. Any provider smoke is bounded,
uses synthetic fixtures, never logs credentials/raw provider payloads, and is
not required for the manual control-room path.
