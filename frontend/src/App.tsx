import { useState } from 'react'
import { DiscoveryView } from './components/DiscoveryView'
import { PlayerPanel } from './components/PlayerPanel'
import { RadioMode } from './components/RadioMode'

function App() {
  const [mode, setMode] = useState<'radio' | 'discovery'>('radio')

  return (
    <div className="h-screen flex overflow-hidden relative" style={{ background: 'var(--color-bg-deep)' }}>
      <div className="flex-1 flex flex-col min-w-0 relative z-10">
        <header
          className="glass-heavy shrink-0 px-6 py-3.5 flex items-center gap-3 border-b"
          style={{ borderColor: 'var(--color-border-subtle)' }}
        >
          <div className="flex items-center gap-2.5">
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center"
              style={{
                background: 'linear-gradient(135deg, var(--color-indigo-mid), var(--color-amber-warm))',
                boxShadow: '0 0 16px rgba(99,102,241,0.25)',
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 18V5l12-2v13" />
                <circle cx="6" cy="18" r="3" />
                <circle cx="18" cy="16" r="3" />
              </svg>
            </div>
            <div>
              <h1 className="brand-text text-xl font-semibold leading-tight">
                Melodia
              </h1>
            </div>
          </div>
          <span
            className="text-xs font-medium tracking-wide uppercase"
            style={{ color: 'var(--color-text-tertiary)' }}
          >
            Custom Radio
          </span>
          <div className="flex-1" />
          <div className="flex gap-1">
            <button
              onClick={() => setMode('radio')}
              className="px-3 py-1.5 rounded-lg text-xs"
              style={{
                background: mode === 'radio' ? 'var(--color-indigo-light)' : 'rgba(255,255,255,0.04)',
                color: mode === 'radio' ? 'white' : 'var(--color-text-secondary)',
              }}
            >
              Radio
            </button>
            <button
              onClick={() => setMode('discovery')}
              className="px-3 py-1.5 rounded-lg text-xs"
              style={{
                background: mode === 'discovery' ? 'var(--color-indigo-light)' : 'rgba(255,255,255,0.04)',
                color: mode === 'discovery' ? 'white' : 'var(--color-text-secondary)',
              }}
            >
              Discover
            </button>
          </div>
        </header>

        <div className="flex-1 min-h-0">
          {mode === 'radio' ? <RadioMode /> : <DiscoveryView />}
        </div>
      </div>

      <div
        className="w-[340px] shrink-0 relative z-10 border-l"
        style={{ borderColor: 'var(--color-border-subtle)' }}
      >
        <PlayerPanel />
      </div>
    </div>
  )
}

export default App
