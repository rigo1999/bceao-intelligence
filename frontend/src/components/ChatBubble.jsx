export default function ChatBubble({ open, onClick }) {
  return (
    <>
      <style>{`
        @keyframes pulse-ring {
          0%   { transform: scale(1);   opacity: 0.6; }
          70%  { transform: scale(1.5); opacity: 0; }
          100% { transform: scale(1.5); opacity: 0; }
        }
        @keyframes bubble-in {
          from { transform: scale(0.4); opacity: 0; }
          to   { transform: scale(1);   opacity: 1; }
        }
        .bubble-btn { animation: bubble-in 0.35s cubic-bezier(.22,.68,0,1.3); }
        .bubble-btn:hover .bubble-inner { transform: scale(1.07); }
      `}</style>

      <button
        className="bubble-btn"
        onClick={onClick}
        aria-label="Ouvrir le chat"
        style={{
          position: 'fixed', bottom: 24, right: 24,
          width: 60, height: 60,
          border: 'none', cursor: 'pointer', background: 'transparent',
          zIndex: 999, padding: 0,
        }}
      >
        {/* Pulse ring */}
        {!open && (
          <span style={{
            position: 'absolute', inset: 0, borderRadius: '50%',
            background: 'rgba(0,48,135,0.35)',
            animation: 'pulse-ring 2s cubic-bezier(0.215,0.61,0.355,1) infinite',
          }} />
        )}

        <div className="bubble-inner" style={{
          position: 'relative', width: '100%', height: '100%',
          borderRadius: '50%',
          background: open
            ? '#e2e8f0'
            : 'linear-gradient(135deg,#003087 0%,#001a4d 100%)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: '0 8px 28px rgba(0,48,135,0.35)',
          transition: 'all 0.22s ease',
        }}>
          {open ? (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <path d="M18 6L6 18M6 6l12 12" stroke="#003087" strokeWidth="2.5" strokeLinecap="round"/>
            </svg>
          ) : (
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
              <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"
                stroke="#C8A045" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                fill="rgba(200,160,69,0.12)"
              />
              <circle cx="8.5"  cy="11" r="1" fill="#C8A045"/>
              <circle cx="12"   cy="11" r="1" fill="#C8A045"/>
              <circle cx="15.5" cy="11" r="1" fill="#C8A045"/>
            </svg>
          )}
        </div>
      </button>
    </>
  )
}
