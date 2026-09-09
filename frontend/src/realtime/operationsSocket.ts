/**
 * Operations realtime WebSocket transport client for SirenGrid.
 * Conforms strictly to SG-INT-05A canonical backend specification.
 *
 * Implements push notification / invalidation transport only.
 * Does NOT store operational state, invoke REST, or wire UI.
 */

import type {
  OperationsEventEnvelope,
  OperationsRecoveryNotice,
  OperationsSocketOptions,
  OperationsSocketState,
} from './types';

export type {
  OperationsEventEnvelope,
  OperationsRecoveryNotice,
  OperationsRecoveryReason,
  OperationsSocketOptions,
  OperationsSocketState,
} from './types';

export const BACKOFF_SCHEDULE_MS = [1000, 2000, 4000, 8000, 10000] as const;

/**
 * Pure helper to derive canonical WebSocket operations URL from an HTTP/HTTPS or WS/WSS base URL.
 * Defaults to import.meta.env.VITE_API_BASE_URL or "ws://localhost:8000/api/v1/ws/operations".
 */
export function buildOperationsWebSocketUrl(apiBaseUrl?: string): string {
  const raw = apiBaseUrl ?? (import.meta.env.VITE_API_BASE_URL as string | undefined);
  if (!raw || raw.trim().length === 0) {
    return 'ws://localhost:8000/api/v1/ws/operations';
  }

  const trimmed = raw.trim().replace(/\/+$/, '');

  let wsUrl = trimmed;
  if (wsUrl.startsWith('https://')) {
    wsUrl = 'wss://' + wsUrl.slice('https://'.length);
  } else if (wsUrl.startsWith('http://')) {
    wsUrl = 'ws://' + wsUrl.slice('http://'.length);
  }

  if (!wsUrl.endsWith('/ws/operations')) {
    wsUrl = `${wsUrl}/ws/operations`;
  }

  return wsUrl;
}

/**
 * Validates and parses a raw unknown value against the canonical OperationsEventEnvelope shape.
 * Returns null if the structure is invalid or any field violates constraints.
 */
export function parseOperationsEnvelope(value: unknown): OperationsEventEnvelope | null {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return null;
  }

  const record = value as Record<string, unknown>;

  if (typeof record.event !== 'string' || record.event.trim().length === 0) {
    return null;
  }

  if (record.incident_id !== null && typeof record.incident_id !== 'string') {
    return null;
  }

  if (typeof record.timestamp !== 'string' || record.timestamp.trim().length === 0) {
    return null;
  }

  if (
    typeof record.version !== 'number' ||
    !Number.isInteger(record.version) ||
    record.version < 1
  ) {
    return null;
  }

  if (
    typeof record.payload !== 'object' ||
    record.payload === null ||
    Array.isArray(record.payload)
  ) {
    return null;
  }

  return {
    event: record.event,
    incident_id: record.incident_id,
    timestamp: record.timestamp,
    version: record.version,
    payload: record.payload as Record<string, unknown>,
  };
}

/**
 * Isolated WebSocket client managing connection lifecycle, deterministic reconnect backoff,
 * sequence tracking, gap/reset detection, and recovery notices for the operations stream.
 */
export class OperationsSocketClient {
  private readonly options: OperationsSocketOptions;
  private readonly url: string;

  private socket: WebSocket | null = null;
  private currentState: OperationsSocketState = 'IDLE';
  private currentLastVersion: number | null = null;

  private isStopped: boolean = false;
  private isReconnecting: boolean = false;
  private reconnectAttempt: number = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(options: OperationsSocketOptions = {}) {
    this.options = options;
    this.url = options.url ? buildOperationsWebSocketUrl(options.url) : buildOperationsWebSocketUrl();
  }

  public get state(): OperationsSocketState {
    return this.currentState;
  }

  public get lastVersion(): number | null {
    return this.currentLastVersion;
  }

  /**
   * Begins connection. Idempotent: no-op if already CONNECTING, OPEN, or RECONNECTING.
   */
  public start(): void {
    if (
      this.currentState === 'OPEN' ||
      this.currentState === 'CONNECTING' ||
      this.currentState === 'RECONNECTING'
    ) {
      return;
    }

    this.isStopped = false;
    this.isReconnecting = false;
    this.reconnectAttempt = 0;
    this.clearReconnectTimer();

    this.setState('CONNECTING');
    this.createWebSocket();
  }

  /**
   * Permanently stops the client until next explicit start().
   * Closes active socket, clears reconnect timers, transitions to CLOSED.
   */
  public stop(): void {
    this.isStopped = true;
    this.isReconnecting = false;
    this.clearReconnectTimer();

    if (this.socket) {
      const ws = this.socket;
      this.socket = null;
      ws.onopen = null;
      ws.onclose = null;
      ws.onerror = null;
      ws.onmessage = null;
      try {
        ws.close();
      } catch {
        // Suppress errors during explicit teardown
      }
    }

    this.setState('CLOSED');
  }

  private createWebSocket(): void {
    if (this.isStopped) {
      return;
    }

    if (this.socket) {
      const prev = this.socket;
      this.socket = null;
      prev.onopen = null;
      prev.onclose = null;
      prev.onerror = null;
      prev.onmessage = null;
      try {
        prev.close();
      } catch {
        // Suppress errors during cleanup of previous socket
      }
    }

    try {
      const ws = new WebSocket(this.url);
      this.socket = ws;

      ws.onopen = () => {
        if (this.isStopped || this.socket !== ws) {
          return;
        }
        this.handleOpen();
      };

      ws.onclose = () => {
        if (this.socket !== ws) {
          return;
        }
        this.handleClose();
      };

      ws.onerror = () => {
        // Section 26: Error event provides no guaranteed detail; close event acts as reconnect trigger.
      };

      ws.onmessage = (event: MessageEvent) => {
        if (this.isStopped || this.socket !== ws) {
          return;
        }
        this.handleMessage(event.data);
      };
    } catch {
      this.handleClose();
    }
  }

  private handleOpen(): void {
    const wasReconnecting = this.isReconnecting;
    this.isReconnecting = false;
    this.reconnectAttempt = 0;
    this.clearReconnectTimer();

    this.setState('OPEN');

    if (wasReconnecting) {
      this.emitRecovery({
        reason: 'RECONNECTED',
        previousVersion: this.currentLastVersion,
        receivedVersion: null,
      });
    }
  }

  private handleClose(): void {
    this.socket = null;

    if (this.isStopped) {
      this.setState('CLOSED');
      return;
    }

    this.isReconnecting = true;
    this.setState('RECONNECTING');
    this.scheduleReconnect();
  }

  private scheduleReconnect(): void {
    this.clearReconnectTimer();

    if (this.isStopped) {
      return;
    }

    const delay = this.getBackoffDelay();
    this.reconnectAttempt++;

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (!this.isStopped) {
        this.createWebSocket();
      }
    }, delay);
  }

  private getBackoffDelay(): number {
    const index = Math.min(this.reconnectAttempt, BACKOFF_SCHEDULE_MS.length - 1);
    return BACKOFF_SCHEDULE_MS[index];
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private handleMessage(rawData: unknown): void {
    if (typeof rawData !== 'string') {
      this.handleMalformed(String(rawData ?? ''));
      return;
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(rawData);
    } catch {
      this.handleMalformed(rawData);
      return;
    }

    const envelope = parseOperationsEnvelope(parsed);
    if (!envelope) {
      this.handleMalformed(rawData);
      return;
    }

    this.processSequence(envelope);
  }

  private handleMalformed(raw: string): void {
    this.options.onMalformedMessage?.(raw);
    this.emitRecovery({
      reason: 'MALFORMED_MESSAGE',
      previousVersion: this.currentLastVersion,
      receivedVersion: null,
    });
  }

  private processSequence(envelope: OperationsEventEnvelope): void {
    const received = envelope.version;
    const previous = this.currentLastVersion;

    if (previous === null) {
      // First observed envelope in client lifetime
      this.currentLastVersion = received;
      this.options.onEnvelope?.(envelope);
      return;
    }

    if (received === previous + 1) {
      // Normal contiguous sequence
      this.currentLastVersion = received;
      this.options.onEnvelope?.(envelope);
      return;
    }

    if (received > previous + 1) {
      // Forward sequence gap
      this.emitRecovery({
        reason: 'SEQUENCE_GAP',
        previousVersion: previous,
        receivedVersion: received,
      });
      this.currentLastVersion = received;
      this.options.onEnvelope?.(envelope);
      return;
    }

    // Sequence reset / backend restart / backwards / duplicate
    this.emitRecovery({
      reason: 'SEQUENCE_RESET',
      previousVersion: previous,
      receivedVersion: received,
    });
    this.currentLastVersion = received;
    this.options.onEnvelope?.(envelope);
  }

  private emitRecovery(notice: OperationsRecoveryNotice): void {
    this.options.onRecoveryRequired?.(notice);
  }

  private setState(nextState: OperationsSocketState): void {
    if (this.currentState === nextState) {
      return;
    }
    this.currentState = nextState;
    this.options.onStateChange?.(nextState);
  }
}
