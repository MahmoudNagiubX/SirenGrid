/**
 * SirenGrid pure recovery notice component (SG-INT-07A).
 * Renders loading, connectivity, staleness, unknown, and recovered operational notices.
 *
 * Reusable presentation only.
 * Does NOT manage React state, establish realtime connections, perform HTTP requests, or schedule retries.
 */

import type { CSSProperties } from 'react';
import { Button } from '../components/Button';
import type { RecoveryNoticeKind, RecoveryNoticeModel } from './recoveryTypes';

export interface RecoveryNoticeProps extends RecoveryNoticeModel {
  onRetry?: () => void;
  retryLabel?: string;
  style?: CSSProperties;
}

interface ToneStyle {
  bg: string;
  fg: string;
  ic: string;
  border: string;
  icon: string;
}

const TONES: Record<RecoveryNoticeKind, ToneStyle> = {
  LOADING: {
    bg: 'var(--color-bg-sunken)',
    fg: 'var(--color-text-secondary)',
    ic: 'var(--color-accent)',
    border: 'var(--color-border-hairline)',
    icon: '◌',
  },
  CONNECTING: {
    bg: 'var(--color-accent-soft)',
    fg: 'var(--blue-700)',
    ic: 'var(--color-accent)',
    border: 'var(--blue-200)',
    icon: 'ⓘ',
  },
  RECONNECTING: {
    bg: 'var(--color-attention-soft)',
    fg: 'var(--gray-800)',
    ic: 'var(--color-attention)',
    border: 'var(--red-100)',
    icon: '⟳',
  },
  DISCONNECTED: {
    bg: 'var(--color-attention-soft)',
    fg: 'var(--gray-800)',
    ic: 'var(--color-attention)',
    border: 'var(--red-100)',
    icon: '!',
  },
  RECOVERED: {
    bg: 'var(--color-confirmed-soft)',
    fg: 'var(--blue-700)',
    ic: 'var(--color-confirmed)',
    border: 'var(--blue-200)',
    icon: '✓',
  },
  STALE: {
    bg: 'var(--color-attention-soft)',
    fg: 'var(--gray-800)',
    ic: 'var(--color-attention)',
    border: 'var(--red-100)',
    icon: '!',
  },
  UNAVAILABLE: {
    bg: 'var(--gray-100)',
    fg: 'var(--gray-700)',
    ic: 'var(--gray-600)',
    border: 'var(--gray-200)',
    icon: '—',
  },
  UNKNOWN: {
    bg: 'var(--gray-100)',
    fg: 'var(--gray-700)',
    ic: 'var(--gray-600)',
    border: 'var(--gray-200)',
    icon: '?',
  },
};

export function RecoveryNotice({
  kind,
  title,
  detail,
  compact = false,
  onRetry,
  retryLabel = 'Retry',
  style,
}: RecoveryNoticeProps) {
  const tone = TONES[kind] ?? TONES.UNKNOWN;
  const isAlert = kind === 'DISCONNECTED' || kind === 'UNAVAILABLE';
  const role = isAlert ? 'alert' : 'status';

  return (
    <div
      role={role}
      aria-live="polite"
      style={{
        display: 'flex',
        alignItems: compact ? 'center' : 'flex-start',
        justifyContent: 'space-between',
        gap: compact ? 8 : 12,
        padding: compact ? '6px 10px' : '10px 14px',
        borderRadius: 'var(--radius-md)',
        background: tone.bg,
        border: `1px solid ${tone.border}`,
        fontFamily: 'var(--font-en)',
        ...style,
      }}
    >
      <div style={{ display: 'flex', gap: compact ? 7 : 10, alignItems: 'flex-start', minWidth: 0, flex: 1 }}>
        <span
          aria-hidden="true"
          style={{
            color: tone.ic,
            fontWeight: 700,
            fontSize: compact ? 12 : 13,
            lineHeight: compact ? '16px' : '18px',
            userSelect: 'none',
            flexShrink: 0,
          }}
        >
          {tone.icon}
        </span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div
            style={{
              fontSize: compact ? 'var(--fs-micro)' : 'var(--fs-caption)',
              fontWeight: 600,
              color: tone.fg,
              lineHeight: compact ? '16px' : '18px',
            }}
          >
            {title}
          </div>
          {detail && !compact && (
            <div
              style={{
                fontSize: 'var(--fs-micro)',
                color: 'var(--color-text-muted)',
                marginTop: 2,
                lineHeight: '16px',
              }}
            >
              {detail}
            </div>
          )}
          {detail && compact && (
            <span
              style={{
                fontSize: 'var(--fs-micro)',
                color: 'var(--color-text-muted)',
                marginLeft: 6,
              }}
            >
              {detail}
            </span>
          )}
        </div>
      </div>
      {onRetry && (
        <div style={{ flexShrink: 0, marginLeft: 8 }}>
          <Button variant="secondary" size="sm" onClick={onRetry}>
            {retryLabel}
          </Button>
        </div>
      )}
    </div>
  );
}
