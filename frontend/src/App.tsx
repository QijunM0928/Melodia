import { DiscoveryView } from './components/DiscoveryView'
import { PlayerPanel } from './components/PlayerPanel'

function App() {
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
            Discovery Workspace
          </span>
        </header>

        <div className="flex-1 min-h-0">
          <DiscoveryView />
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
