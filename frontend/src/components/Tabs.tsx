import { useState } from 'react';

/** Ported from components/navigation/Tabs.jsx — segmented tab switcher. */
export interface TabItem {
  value: string;
  label: string;
}

export interface TabsProps {
  tabs?: TabItem[];
  defaultValue?: string;
  onChange?: (value: string) => void;
}

export function Tabs({ tabs = [], defaultValue, onChange }: TabsProps) {
  const [active, setActive] = useState(defaultValue ?? tabs[0]?.value);
  return (
    <div role="tablist" style={{ display: 'flex', gap: 4, background: 'var(--gray-100)', padding: 4, borderRadius: 'var(--radius-md)', fontFamily: 'var(--font-en)', width: 'fit-content' }}>
      {tabs.map((t) => {
        const isActive = t.value === active;
        return (
          <button
            key={t.value}
            role="tab"
            aria-selected={isActive}
            onClick={() => { setActive(t.value); onChange?.(t.value); }}
            style={{
              padding: '7px 16px',
              borderRadius: 'var(--radius-sm)',
              border: 'none',
              cursor: 'pointer',
              background: isActive ? 'var(--color-bg-surface)' : 'transparent',
              color: isActive ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
              fontSize: 'var(--fs-caption)',
              fontWeight: 500,
              boxShadow: isActive ? 'var(--shadow-xs)' : 'none',
            }}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
