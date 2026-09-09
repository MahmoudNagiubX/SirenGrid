/**
 * Operations realtime WebSocket transport types for SirenGrid.
 * Conforms strictly to SG-INT-05A canonical backend specification.
 */

export interface OperationsEventEnvelope {
  event: string;
  incident_id: string | null;
  timestamp: string;
  version: number;
  payload: Record<string, unknown>;
}

export type OperationsSocketState =
  | 'IDLE'
  | 'CONNECTING'
  | 'OPEN'
  | 'RECONNECTING'
  | 'CLOSED';

export type OperationsRecoveryReason =
  | 'RECONNECTED'
  | 'SEQUENCE_GAP'
  | 'SEQUENCE_RESET'
  | 'MALFORMED_MESSAGE';

export interface OperationsRecoveryNotice {
  reason: OperationsRecoveryReason;
  previousVersion: number | null;
  receivedVersion: number | null;
}

export interface OperationsSocketOptions {
  url?: string;
  onEnvelope?: (envelope: OperationsEventEnvelope) => void;
  onStateChange?: (state: OperationsSocketState) => void;
  onRecoveryRequired?: (notice: OperationsRecoveryNotice) => void;
  onMalformedMessage?: (raw: string) => void;
}
