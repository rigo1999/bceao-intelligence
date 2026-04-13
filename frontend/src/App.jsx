import { useState } from 'react'
import ChatPanel from './components/ChatPanel'
import ChatBubble from './components/ChatBubble'

const STATS = [
  { value: '8', label: 'États membres', sub: 'de l\'UEMOA' },
  { value: '180M+', label: 'Habitants', sub: 'zone couverte' },
  { value: '1994', label: 'Fondée en', sub: 'Dakar, Sénégal' },
]

export default function App() {
  const [open, setOpen] = useState(false)

  return (
    <>
      <style>{`
        @keyframes fadeUp {
          from { opacity:0; transform:translateY(24px); }
          to   { opacity:1; transform:translateY(0); }
        }
        @keyframes shimmer {
          0%   { background-position: -400px 0; }
          100% { background-position:  400px 0; }
        }
        .hero-title {
          background: linear-gradient(135deg, #003087 30%, #C8A045 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
        }
        .stat-card:hover { transform: translateY(-4px); box-shadow: 0 12px 32px rgba(0,48,135,0.12) !important; }
        .nav-link:hover  { color: #003087 !important; }
        .cta-btn:hover   { transform: translateY(-2px); box-shadow: 0 12px 28px rgba(0,48,135,0.28) !important; }
      `}</style>

      <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>

        {/* ── Nav ── */}
        <nav style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '0 48px', height: 64,
          background: '#fff',
          borderBottom: '1px solid #e2e8f0',
          position: 'sticky', top: 0, zIndex: 100,
          boxShadow: '0 1px 12px rgba(0,48,135,0.06)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 38, height: 38, borderRadius: 10,
              background: 'linear-gradient(135deg,#003087,#002060)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: '#C8A045', fontWeight: 800, fontSize: 18,
            }}>B</div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 15, color: '#003087', lineHeight: 1.1 }}>BCEAO</div>
              <div style={{ fontSize: 10, color: '#6b7a99', letterSpacing: '0.04em' }}>Assistant IA</div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 32 }}>
            {['Politique monétaire', 'Système bancaire', 'UEMOA', 'Publications'].map(l => (
              <a key={l} className="nav-link" href="#" style={{
                fontSize: 13.5, color: '#6b7a99', textDecoration: 'none',
                fontWeight: 500, transition: 'color 0.15s',
              }}>{l}</a>
            ))}
          </div>

          <button onClick={() => setOpen(true)} style={{
            background: 'linear-gradient(135deg,#003087,#002060)',
            color: '#C8A045', border: 'none', cursor: 'pointer',
            padding: '9px 18px', borderRadius: 10, fontSize: 13, fontWeight: 600,
            fontFamily: 'inherit', transition: 'opacity 0.15s',
          }}>
            Poser une question
          </button>
        </nav>

        {/* ── Hero ── */}
        <section style={{
          flex: 1,
          background: 'linear-gradient(160deg, #f0f4ff 0%, #faf9f4 50%, #fff8ed 100%)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          padding: '80px 48px',
          position: 'relative', overflow: 'hidden',
        }}>

          {/* Background decoration */}
          <div style={{
            position: 'absolute', top: -120, right: -120,
            width: 480, height: 480, borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(0,48,135,0.06) 0%, transparent 70%)',
            pointerEvents: 'none',
          }} />
          <div style={{
            position: 'absolute', bottom: -80, left: -80,
            width: 360, height: 360, borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(200,160,69,0.08) 0%, transparent 70%)',
            pointerEvents: 'none',
          }} />

          <div style={{
            maxWidth: 780, textAlign: 'center',
            animation: 'fadeUp 0.7s ease both',
          }}>

            {/* Pill badge */}
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 7,
              background: 'rgba(0,48,135,0.07)', border: '1px solid rgba(0,48,135,0.14)',
              borderRadius: 100, padding: '6px 16px', marginBottom: 32,
            }}>
              <span style={{ width: 7, height: 7, background: '#4ade80', borderRadius: '50%', display: 'inline-block' }} />
              <span style={{ fontSize: 12.5, color: '#003087', fontWeight: 600, letterSpacing: '0.03em' }}>
                Intelligence Artificielle · RAG BCEAO
              </span>
            </div>

            <h1 className="hero-title" style={{
              fontSize: 'clamp(36px, 6vw, 60px)',
              fontWeight: 800, lineHeight: 1.12,
              marginBottom: 24, letterSpacing: '-0.02em',
            }}>
              Explorez les données<br />de la BCEAO
            </h1>

            <p style={{
              fontSize: 18, color: '#6b7a99', lineHeight: 1.7,
              maxWidth: 540, margin: '0 auto 40px', fontWeight: 400,
            }}>
              Posez vos questions sur la politique monétaire, le système bancaire
              et l'économie de l'UEMOA — réponses instantanées issues des documents officiels.
            </p>

            <button
              className="cta-btn"
              onClick={() => setOpen(true)}
              style={{
                background: 'linear-gradient(135deg,#003087 0%,#002060 100%)',
                color: '#C8A045', border: 'none', cursor: 'pointer',
                padding: '16px 36px', borderRadius: 14, fontSize: 15, fontWeight: 700,
                fontFamily: 'inherit', letterSpacing: '0.01em',
                boxShadow: '0 8px 24px rgba(0,48,135,0.22)',
                transition: 'all 0.22s ease',
              }}
            >
              Démarrer une conversation →
            </button>

            {/* Stats */}
            <div style={{
              display: 'flex', justifyContent: 'center', gap: 20,
              marginTop: 64, flexWrap: 'wrap',
            }}>
              {STATS.map(s => (
                <div key={s.label} className="stat-card" style={{
                  background: '#fff', borderRadius: 16,
                  padding: '20px 28px', minWidth: 140,
                  border: '1px solid #e2e8f0',
                  boxShadow: '0 2px 12px rgba(0,48,135,0.06)',
                  transition: 'all 0.22s ease', cursor: 'default',
                }}>
                  <div style={{ fontSize: 28, fontWeight: 800, color: '#003087', lineHeight: 1 }}>
                    {s.value}
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#1a2236', marginTop: 5 }}>
                    {s.label}
                  </div>
                  <div style={{ fontSize: 11, color: '#6b7a99', marginTop: 2 }}>
                    {s.sub}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ── Footer ── */}
        <footer style={{
          background: '#fff', borderTop: '1px solid #e2e8f0',
          padding: '18px 48px', display: 'flex',
          justifyContent: 'space-between', alignItems: 'center',
        }}>
          <span style={{ fontSize: 12, color: '#94a3b8' }}>
            © 2025 BCEAO — Banque Centrale des États de l'Afrique de l'Ouest
          </span>
          <span style={{ fontSize: 12, color: '#94a3b8' }}>
            Alimenté par RAG · Ollama · ChromaDB
          </span>
        </footer>
      </div>

      {/* ── Chatbot ── */}
      {open && <ChatPanel onClose={() => setOpen(false)} />}
      <ChatBubble open={open} onClick={() => setOpen(o => !o)} />
    </>
  )
}
