import { useEffect, useState } from 'react';
import { StatusStrip } from './ops/workspace';
import { Operations } from './ops/Operations';
import { ResourceScreen } from './ops/screens-resources';
import { BenchmarkScreen, DemoScreen } from './ops/screens-support';
import { Landing } from './pages/Landing';
import { STATE_META, type OpsState, type TopNav } from './data/mock';

type View = 'landing' | TopNav;

/** Deep-link support mirroring the design's `state-*.html` wrappers (index.html#<state>). */
function readHashState(): OpsState {
  const h = (typeof location !== 'undefined' ? location.hash : '').replace(/^#\/?/, '');
  return (h in STATE_META ? h : 'idle') as OpsState;
}

/**
 * Ported from the `App` component in ui_kits/operations_center/index.html.
 * The Landing screen is its own full-bleed page; every other view shares the Operations shell
 * (persistent StatusStrip + one screen).
 */
export function App() {
  const [view, setView] = useState<View>(() => (readHashState() !== 'idle' ? 'operations' : 'landing'));
  const [opsState, setOpsState] = useState<OpsState>(readHashState);

  useEffect(() => {
    const onHash = () => {
      const s = readHashState();
      if (s !== 'idle') {
        setOpsState(s);
        setView('operations');
      }
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  if (view === 'landing') {
    return (
      <div style={{ height: '100vh', overflow: 'hidden' }}>
        <Landing onLaunch={() => setView('operations')} />
      </div>
    );
  }

  return (
    <div style={{ height: '100vh', overflowX: 'auto', overflowY: 'hidden' }}>
      <div
        style={{
          minWidth: 1440,
          height: '100vh',
          display: 'flex',
          flexDirection: 'column',
          background: 'var(--color-bg-app)',
          fontFamily: 'var(--font-en)',
          color: 'var(--color-text-primary)',
        }}
      >
        <StatusStrip nav={view} setNav={(n) => (n === 'landing' ? setView('landing') : setView(n))} />
        {view === 'operations' && <Operations key={opsState} initialState={opsState} />}
        {view === 'resources' && <ResourceScreen />}
        {view === 'benchmark' && <BenchmarkScreen />}
        {view === 'demo' && <DemoScreen />}
      </div>
    </div>
  );
}
