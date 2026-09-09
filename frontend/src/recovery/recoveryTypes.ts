/**
 * SirenGrid pure recovery presentation types (SG-INT-07A).
 * Defines models and pure derivations for loading, stale, unknown, and connectivity states.
 *
 * Does NOT invoke network APIs, manage state, or implement retry loops.
 */

import type { OperationsRecoveryReason, OperationsSocketState } from '../realtime/types';

export type RecoveryNoticeKind =
  | 'LOADING'
  | 'UNAVAILABLE'
  | 'STALE'
  | 'UNKNOWN'
  | 'CONNECTING'
  | 'RECONNECTING'
  | 'DISCONNECTED'
  | 'RECOVERED';

export interface RecoveryNoticeModel {
  kind: RecoveryNoticeKind;
  title: string;
  detail?: string;
  compact?: boolean;
}

export interface RealtimePresentationInput {
  state: OperationsSocketState;
  recoveryReason?: OperationsRecoveryReason | null;
}

/**
 * Pure derivation converting realtime transport state into an operator-facing recovery notice.
 * Returns null when transport is normal (OPEN with no pending recovery).
 */
export function deriveRealtimeNotice(input: RealtimePresentationInput): RecoveryNoticeModel | null {
  const { state, recoveryReason } = input;

  if (state === 'IDLE' || state === 'CONNECTING') {
    return {
      kind: 'CONNECTING',
      title: 'Connecting to live updates',
      detail: 'Operational data continues to come from REST.',
    };
  }

  if (state === 'RECONNECTING') {
    return {
      kind: 'RECONNECTING',
      title: 'Reconnecting live updates',
      detail: 'Canonical state will be reconciled from the API.',
    };
  }

  if (state === 'CLOSED') {
    return {
      kind: 'DISCONNECTED',
      title: 'Live updates disconnected',
      detail: 'Displayed data may not reflect the latest committed change until REST recovery succeeds.',
    };
  }

  if (state === 'OPEN') {
    if (recoveryReason) {
      return {
        kind: 'RECOVERED',
        title: 'Live stream recovered',
        detail: 'Canonical REST reconciliation was requested.',
        compact: true,
      };
    }
    return null;
  }

  return null;
}
