/**
 * Presentation-only readers for Team 01 mobile-origin incident/report provenance.
 *
 * These helpers ONLY read the safe context that the backend intentionally
 * embeds in `Incident.provenance` / `Report.provenance` for a `MOBILE_APP`
 * request (see backend/app/mobile_api.py `_build_mobile_provenance`). They:
 *
 *  - never throw on missing / legacy / non-mobile provenance,
 *  - return `null` / `false` / empty for anything that is not mobile-origin so
 *    existing non-mobile incident presentation is untouched,
 *  - compute no operational state (severity, ETA, routing, coverage, dispatch),
 *  - expose no auth/session material. The backend provenance already contains
 *    only a MASKED national id; PIN, tokens, hashes, salts and the full
 *    national id are never present and are never read here.
 *
 * Registered address and the current emergency Device-GPS location are kept
 * strictly separate: the registered address is account context only and lives
 * in `getMobileCitizenContext(...)`, while the operational emergency location
 * comes from the incident's own `latitude` / `longitude` and its GPS metadata
 * lives in `getMobileLocationSummary(...)`.
 */

/** Exact backend constants — kept in sync with backend/app/mobile_api.py. */
export const MOBILE_SOURCE_TYPE = 'MOBILE_APP';
export const MOBILE_SOURCE = 'SIRENGRID_CITIZEN_APP';
export const UNCONFIRMED_MOBILE_SEVERITY_AUTHORITY = 'UNCONFIRMED_MOBILE_PLACEHOLDER';

/** Anything carrying backend provenance (IncidentRead, ReportRead, …). */
export interface ProvenanceBearer {
  source_type?: string | null;
  provenance?: Record<string, unknown> | null;
  provenance_json?: Record<string, unknown> | null;
}

/** Safe operator-facing citizen account context (all fields may be absent). */
export interface MobileCitizenContext {
  citizenReference: string | null;
  displayName: string | null;
  phone: string | null;
  /** Account/profile address — NOT the emergency location. */
  registeredAddress: string | null;
  /** Already masked by the backend, e.g. "**********1234". */
  nationalIdMasked: string | null;
  identityStatus: string | null;
}

/** Compact summary of how a mobile request entered SirenGrid. */
export interface MobileSourceSummary {
  source: string;
  /** Locked service the citizen tapped: AMBULANCE | FIRE | POLICE | GENERAL. */
  requestedService: string | null;
  locationSource: string | null;
  /** POLICE / GENERAL (or an explicit review/handoff flag) → operator review only. */
  operatorReviewRequired: boolean;
}

/** Emergency-location metadata (the coordinates themselves are on the incident). */
export interface MobileLocationSummary {
  locationSource: string | null;
  locationAccuracyM: number | null;
  clientTimestamp: string | null;
}

function readProvenance(x: ProvenanceBearer | null | undefined): Record<string, unknown> {
  if (!x || typeof x !== 'object') return {};
  const prov = x.provenance ?? x.provenance_json;
  return prov && typeof prov === 'object' ? (prov as Record<string, unknown>) : {};
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}

function asFiniteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
}

/**
 * True when the incident/report originated from the SirenGrid Citizen app.
 * Tolerant of both the top-level `source_type` and the provenance copy.
 */
export function isMobileOrigin(x: ProvenanceBearer | null | undefined): boolean {
  if (!x) return false;
  if (asString(x.source_type) === MOBILE_SOURCE_TYPE) return true;
  const prov = readProvenance(x);
  return (
    asString(prov.source_type) === MOBILE_SOURCE_TYPE ||
    asString(prov.source) === MOBILE_SOURCE
  );
}

/** `MobileSourceSummary` for a mobile-origin record, else `null`. */
export function getMobileSourceSummary(
  x: ProvenanceBearer | null | undefined,
): MobileSourceSummary | null {
  if (!isMobileOrigin(x)) return null;
  const prov = readProvenance(x);
  return {
    source: asString(prov.source) ?? MOBILE_SOURCE,
    requestedService: asString(prov.requested_service),
    locationSource: asString(prov.location_source),
    operatorReviewRequired:
      prov.operator_review_required === true ||
      prov.operator_handoff_required === true ||
      asString(prov.service_disposition) === 'OPERATOR_HANDOFF' ||
      asString(prov.service_disposition) === 'OPERATOR_REVIEW',
  };
}

/**
 * True when the stored severity is only a mobile placeholder and must NOT be
 * shown as an authoritative severity.
 */
export function isUnconfirmedMobileSeverity(
  x: ProvenanceBearer | null | undefined,
): boolean {
  if (!x) return false;
  const prov = readProvenance(x);
  return asString(prov.severity_authority) === UNCONFIRMED_MOBILE_SEVERITY_AUTHORITY;
}

/** Safe citizen account context for a mobile-origin record, else `null`. */
export function getMobileCitizenContext(
  x: ProvenanceBearer | null | undefined,
): MobileCitizenContext | null {
  if (!isMobileOrigin(x)) return null;
  const ctx = asRecord(readProvenance(x).citizen_context);
  return {
    citizenReference: asString(ctx.citizen_reference),
    displayName: asString(ctx.display_name),
    phone: asString(ctx.phone),
    registeredAddress: asString(ctx.registered_address),
    nationalIdMasked: asString(ctx.national_id_masked),
    identityStatus: asString(ctx.identity_status),
  };
}

/**
 * GPS metadata for the current emergency location. The coordinates themselves
 * are the incident's own `latitude` / `longitude`; this never returns the
 * registered address.
 */
export function getMobileLocationSummary(
  x: ProvenanceBearer | null | undefined,
): MobileLocationSummary | null {
  if (!isMobileOrigin(x)) return null;
  const prov = readProvenance(x);
  return {
    locationSource: asString(prov.location_source),
    locationAccuracyM: asFiniteNumber(prov.location_accuracy_m),
    clientTimestamp: asString(prov.client_timestamp),
  };
}
