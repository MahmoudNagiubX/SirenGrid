import type { CSSProperties, ReactNode } from 'react';

/** Ported from components/surfaces/Card.jsx — opaque surface for content nested inside glass or in dense contexts. */
export interface CardProps {
  children: ReactNode;
  padding?: number;
  style?: CSSProperties;
}

export function Card({ children, padding = 20, style = {} }: CardProps) {
  return (
    <div
      style={{
        background: 'var(--color-bg-surface)',
        border: '1px solid var(--color-border-hairline)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: 'var(--shadow-sm)',
        padding,
        ...style,
      }}
    >
      {children}
    </div>
  );
}
