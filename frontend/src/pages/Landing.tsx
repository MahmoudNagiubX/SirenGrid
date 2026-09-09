import { Badge, Button, GlassPanel, IconTile } from '../components';
import { Ico } from '../lib/icon';
import { DenseMap, FacilityPin } from '../ops/DenseMap';
import { GLASS_CHIP } from '../ops/glassChip';
import { LANDING_INCIDENT_STATS, LANDING_STEPS } from '../data/mock';

/**
 * Ported from ui_kits/landing/index.html — single-screen product landing over a live Cairo
 * map ground, with a light diagonal wash and floating glass panels.
 */
export function Landing({ onLaunch }: { onLaunch: () => void }) {
  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', overflow: 'hidden', background: 'var(--color-bg-app)', fontFamily: 'var(--font-en)', color: 'var(--color-text-primary)' }}>
      <div style={{ position: 'absolute', inset: '-6% -4%', animation: 'sg-drift 34s ease-in-out infinite' }}>
        <DenseMap view="city" route="plan" overlays={{ traffic: true }} />
      </div>
      <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(100deg, rgba(245,247,251,.93) 0%, rgba(245,247,251,.88) 40%, rgba(236,241,248,.72) 58%, rgba(236,241,248,.6) 100%)' }} />
      <div style={{ position: 'relative', height: '100%', display: 'flex', flexDirection: 'column' }}>
        <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '26px 56px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
            <span style={{ width: 11, height: 11, borderRadius: '50%', background: 'var(--red-500)', boxShadow: '0 0 0 7px rgba(239,35,60,.16)' }} />
            <span style={{ fontWeight: 700, fontSize: 21, letterSpacing: '-0.02em' }}>SirenGrid</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <span dir="rtl" style={{ fontFamily: 'var(--font-ar)', fontSize: 15, color: 'var(--color-text-secondary)' }}>مدينة نصر · القاهرة</span>
            <Badge tone="simulated">Prototype</Badge>
          </div>
        </header>
        <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 1fr', alignItems: 'center', gap: 40, padding: '0 56px 40px' }}>
          <div className="sg-rise" style={{ maxWidth: 540 }}>
            <h1 style={{ fontSize: 54, lineHeight: 1.06, letterSpacing: '-0.035em', fontWeight: 600, margin: 0, textWrap: 'balance' }}>
              Emergency response, coordinated as one system.
            </h1>
            <p style={{ fontSize: 18, lineHeight: 1.55, color: 'var(--color-text-secondary)', margin: '20px 0 28px', maxWidth: 470, textWrap: 'pretty' }}>
              AI-assisted coordination across responders, roads, city coverage and hospitals — every critical action approved by a human
              operator.
            </p>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
              <Button
                variant="primary"
                size="lg"
                onClick={onLaunch}
                icon={
                  <span style={{ width: 18, height: 18, display: 'flex' }}>
                    <Ico n="arrow-right" />
                  </span>
                }
              >
                Launch Operations Center
              </Button>
              <Button variant="secondary" size="lg">Watch the 90-second story</Button>
            </div>
            <div style={{ display: 'flex', gap: 26, marginTop: 42, flexWrap: 'wrap' }}>
              {LANDING_STEPS.map(([s, i], k) => (
                <div key={s} style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                  <IconTile icon={<Ico n={i} />} tint={k === 3 ? 'red' : 'navy'} size={32} />
                  <span style={{ fontSize: 15, fontWeight: 600 }}>{s}</span>
                </div>
              ))}
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14, alignItems: 'flex-end' }}>
            <GlassPanel padding={10} style={{ width: 560 }}>
              <div style={{ position: 'relative', height: 320, borderRadius: 'var(--radius-md)', overflow: 'hidden', border: '1px solid var(--color-border-hairline)' }}>
                <DenseMap view="incident" route="plan" overlays={{ traffic: true, corridor: true }}>
                  <div style={{ position: 'absolute', left: '38%', top: '28%', display: 'flex', alignItems: 'center', gap: 9, padding: '5px 12px 5px 5px', borderRadius: 'var(--radius-md)', whiteSpace: 'nowrap', ...GLASS_CHIP }}>
                    <IconTile icon={<Ico n="triangle-alert" />} tint="red" shape="circle" size={28} />
                    <span style={{ fontSize: 13, fontWeight: 600 }}>INC-2418</span>
                  </div>
                  <div style={{ position: 'absolute', left: '9%', top: '72%', display: 'flex', alignItems: 'center', gap: 9, padding: '5px 12px 5px 5px', borderRadius: 'var(--radius-md)', whiteSpace: 'nowrap', ...GLASS_CHIP }}>
                    <IconTile icon={<Ico n="ambulance" />} tint="blue" shape="circle" size={28} />
                    <span style={{ fontSize: 13, fontWeight: 600 }}>A1 · 6:20</span>
                  </div>
                  <FacilityPin icon="hospital" label="El Nozha" tone="navy" left="74%" top="16%" />
                  <FacilityPin icon="flame" label="Fire Stn. 4" tone="red" left="26%" top="84%" />
                </DenseMap>
              </div>
            </GlassPanel>
            <GlassPanel padding={18} style={{ width: 470 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <IconTile icon={<Ico n="triangle-alert" />} tint="red" size={42} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 17, fontWeight: 600 }}>INC-2418 · Road Traffic Accident</div>
                  <div style={{ fontSize: 14, color: 'var(--color-text-muted)' }}>Abbas El Akkad × Makram Ebeid · 20:58</div>
                </div>
                <Badge severity="critical" />
              </div>
              <div style={{ display: 'flex', gap: 22, marginTop: 16, paddingTop: 14, borderTop: '1px solid var(--color-border-hairline)' }}>
                {LANDING_INCIDENT_STATS.map(([v, l]) => (
                  <div key={l}>
                    <div style={{ fontSize: 20, fontWeight: 600, letterSpacing: '-0.015em' }}>{v}</div>
                    <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>{l}</div>
                  </div>
                ))}
              </div>
            </GlassPanel>
            <GlassPanel padding={16} style={{ width: 400 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
                <IconTile icon={<Ico n="user-round-check" />} tint="navy" size={34} />
                <div>
                  <div style={{ fontSize: 15, fontWeight: 600 }}>Human approval, always</div>
                  <div style={{ fontSize: 13.5, color: 'var(--color-text-muted)' }}>AI proposes · the operator decides</div>
                </div>
              </div>
            </GlassPanel>
          </div>
        </div>
      </div>
    </div>
  );
}
