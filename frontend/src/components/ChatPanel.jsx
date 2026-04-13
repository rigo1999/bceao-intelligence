import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'

const MARKER_LOCAL = '<<SOURCE:LOCAL>>'
const MARKER_WEB = '<<SOURCE:WEB>>'
const MARKER_CACHE = '<<SOURCE:CACHE>>'
const MARKERS = [MARKER_LOCAL, MARKER_WEB, MARKER_CACHE]

const SUGGESTIONS = [
  'Qu\'est-ce que la BCEAO ?',
  'Que parle du rapport de 2023 sur les activité de la BCEAO ?',
  'Comment fonctionne le système de paiement UEMOA ?',
]

function SourceBadge({ source }) {
  if (!source) return null
  const map = {
    LOCAL: { label: 'Base locale', color: '#003087' },
    WEB: { label: 'Web', color: '#8B5CF6' },
    CACHE: { label: 'Cache', color: '#059669' },
  }
  const s = map[source]
  if (!s) return null
  return (
    <span style={{
      fontSize: 10, fontWeight: 600, letterSpacing: '0.05em',
      color: s.color, background: s.color + '18',
      borderRadius: 6, padding: '2px 7px', display: 'inline-block',
      marginBottom: 4, textTransform: 'uppercase',
    }}>
      {s.label}
    </span>
  )
}

function Message({ msg }) {
  const isUser = msg.role === 'user'
  return (
    <div style={{
      display: 'flex',
      justifyContent: isUser ? 'flex-end' : 'flex-start',
      marginBottom: 14,
      gap: 8,
      alignItems: 'flex-end',
    }}>
      {!isUser && (
        <div style={{
          width: 28, height: 28, borderRadius: '50%',
          background: 'linear-gradient(135deg,#003087,#002060)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0, fontSize: 13, color: '#C8A045', fontWeight: 700,
        }}>B</div>
      )}

      <div style={{ maxWidth: '80%' }}>
        {!isUser && <SourceBadge source={msg.source} />}
        <div style={{
          background: isUser
            ? 'linear-gradient(135deg,#003087,#002060)'
            : '#ffffff',
          color: isUser ? '#ffffff' : '#1a2236',
          borderRadius: isUser ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
          padding: '10px 14px',
          fontSize: 13.5,
          lineHeight: 1.6,
          boxShadow: '0 1px 6px rgba(0,0,0,0.07)',
          border: isUser ? 'none' : '1px solid #e2e8f0',
        }}>
          {msg.typing ? (
            <TypingDots />
          ) : (
            <div className="md-body">
              <ReactMarkdown>{msg.content}</ReactMarkdown>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function TypingDots() {
  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'center', height: 20 }}>
      {[0, 1, 2].map(i => (
        <span key={i} style={{
          width: 6, height: 6, borderRadius: '50%',
          background: '#C8A045',
          animation: 'blink 1.2s infinite',
          animationDelay: `${i * 0.2}s`,
        }} />
      ))}
    </div>
  )
}

export default function ChatPanel({ onClose }) {
  const [messages, setMessages] = useState([{
    role: 'assistant',
    content: 'Bonjour ! Je suis l\'assistant IA de la BCEAO. Posez-moi vos questions sur la politique monétaire, le système bancaire de l\'UEMOA et plus encore.',
    source: null,
  }])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  async function sendMessage(text) {
    const question = (text || input).trim()
    if (!question || loading) return

    // Capturer l'historique AVANT d'ajouter la nouvelle question
    const history = messages
      .filter(m => !m.typing && m.content)
      .map(m => ({ role: m.role, content: m.content }))

    setInput('')
    setMessages(prev => [...prev,
    { role: 'user', content: question },
    { role: 'assistant', content: '', typing: true, source: null },
    ])
    setLoading(true)

    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 60000)

    try {
      const res = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, history }),
        signal: controller.signal,
      })
      clearTimeout(timeout)

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let source = null
      let fullText = ''
      let firstChunk = true

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        for (const line of lines) {
          if (line.startsWith(': ')) continue          // SSE comments (ping)
          if (!line.startsWith('data: ')) continue
          const raw = line.slice(6)
          if (raw === '[DONE]') break

          // Tokens are JSON-encoded to survive newlines in SSE
          let data
          try { data = JSON.parse(raw) } catch { data = raw }

          if (MARKERS.includes(data)) {
            source = data.replace('<<SOURCE:', '').replace('>>', '')
            continue
          }

          fullText += data
          firstChunk = false  // mutate outside updater — StrictMode safe

          setMessages(prev => {
            const updated = [...prev]
            const last = { ...updated[updated.length - 1] }
            last.typing = false   // always false once content flows
            last.content = fullText
            last.source = source
            updated[updated.length - 1] = last
            return updated
          })
        }
      }
    } catch (err) {
      clearTimeout(timeout)
      const msg = err.name === 'AbortError'
        ? 'Délai dépassé (60s). Le modèle est peut-être en cours de chargement, réessayez.'
        : 'Serveur non disponible. Démarrez le backend : `uvicorn api:app --port 8000`'
      setMessages(prev => {
        const updated = [...prev]
        updated[updated.length - 1] = {
          role: 'assistant', content: msg, source: null,
        }
        return updated
      })
    } finally {
      setLoading(false)
    }
  }

  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
  }

  return (
    <>
      <style>{`
        @keyframes blink {
          0%,80%,100% { opacity: 0.2; transform: scale(0.8); }
          40%          { opacity: 1;   transform: scale(1); }
        }
        @keyframes slideUp {
          from { opacity: 0; transform: translateY(30px) scale(0.96); }
          to   { opacity: 1; transform: translateY(0)    scale(1); }
        }
        .md-body p    { margin-bottom: 6px; }
        .md-body ul   { padding-left: 18px; margin-bottom: 6px; }
        .md-body ol   { padding-left: 18px; margin-bottom: 6px; }
        .md-body li   { margin-bottom: 3px; }
        .md-body strong { color: #003087; }
        .chat-input:focus { outline: none; }
        .send-btn:hover { opacity: 0.88; transform: scale(1.04); }
        .suggestion-btn:hover { background: #003087 !important; color: #fff !important; }
      `}</style>

      <div style={{
        position: 'fixed', bottom: 90, right: 24,
        width: 380, height: 580,
        background: '#F5F7FA',
        borderRadius: 24,
        boxShadow: '0 24px 60px rgba(0,48,135,0.18), 0 4px 16px rgba(0,0,0,0.1)',
        display: 'flex', flexDirection: 'column',
        overflow: 'hidden',
        animation: 'slideUp 0.28s cubic-bezier(.22,.68,0,1.2)',
        zIndex: 1000,
        border: '1px solid rgba(0,48,135,0.08)',
      }}>

        {/* Header */}
        <div style={{
          background: 'linear-gradient(135deg,#003087 0%,#002060 100%)',
          padding: '16px 18px',
          display: 'flex', alignItems: 'center', gap: 12,
          flexShrink: 0,
        }}>
          <div style={{
            width: 40, height: 40, borderRadius: '50%',
            background: 'rgba(200,160,69,0.25)',
            border: '2px solid #C8A045',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 18, fontWeight: 800, color: '#C8A045',
            flexShrink: 0,
          }}>B</div>

          <div style={{ flex: 1 }}>
            <div style={{ color: '#fff', fontWeight: 600, fontSize: 14 }}>
              Assistant BCEAO
            </div>
            <div style={{ color: 'rgba(255,255,255,0.65)', fontSize: 11, display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 7, height: 7, background: '#4ade80', borderRadius: '50%', display: 'inline-block' }} />
              IA • Politique monétaire & UEMOA
            </div>
          </div>

          <button onClick={onClose} style={{
            background: 'rgba(255,255,255,0.12)', border: 'none', cursor: 'pointer',
            color: '#fff', width: 30, height: 30, borderRadius: '50%',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 16, transition: 'background 0.15s',
          }}>×</button>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 14px', display: 'flex', flexDirection: 'column' }}>
          {messages.map((msg, i) => <Message key={i} msg={msg} />)}

          {/* Suggestions — show only at start */}
          {messages.length === 1 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 7, marginTop: 4 }}>
              {SUGGESTIONS.map(s => (
                <button key={s} className="suggestion-btn" onClick={() => sendMessage(s)} style={{
                  background: '#fff', border: '1px solid #e2e8f0',
                  borderRadius: 10, padding: '8px 12px', cursor: 'pointer',
                  fontSize: 12.5, color: '#003087', textAlign: 'left',
                  transition: 'all 0.15s', fontFamily: 'inherit',
                }}>
                  {s}
                </button>
              ))}
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div style={{
          padding: '12px 14px 14px',
          background: '#fff',
          borderTop: '1px solid #e2e8f0',
          flexShrink: 0,
        }}>
          <div style={{
            display: 'flex', alignItems: 'flex-end', gap: 8,
            background: '#F5F7FA',
            borderRadius: 14, padding: '8px 8px 8px 14px',
            border: '1.5px solid #e2e8f0',
          }}>
            <textarea
              ref={inputRef}
              className="chat-input"
              rows={1}
              value={input}
              onChange={e => { setInput(e.target.value); e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 100) + 'px' }}
              onKeyDown={handleKey}
              placeholder="Posez votre question…"
              disabled={loading}
              style={{
                flex: 1, border: 'none', background: 'transparent',
                resize: 'none', fontSize: 13.5, lineHeight: 1.5,
                color: '#1a2236', fontFamily: 'inherit',
                maxHeight: 100, overflowY: 'auto',
              }}
            />
            <button
              className="send-btn"
              onClick={() => sendMessage()}
              disabled={loading || !input.trim()}
              style={{
                width: 36, height: 36, borderRadius: 10,
                background: input.trim() && !loading
                  ? 'linear-gradient(135deg,#003087,#002060)'
                  : '#e2e8f0',
                border: 'none', cursor: input.trim() && !loading ? 'pointer' : 'default',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'all 0.15s', flexShrink: 0,
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                <path d="M22 2L11 13" stroke={input.trim() && !loading ? '#C8A045' : '#94a3b8'} strokeWidth="2.5" strokeLinecap="round" />
                <path d="M22 2L15 22L11 13L2 9L22 2Z" stroke={input.trim() && !loading ? '#C8A045' : '#94a3b8'} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
          <p style={{ fontSize: 10, color: '#94a3b8', textAlign: 'center', marginTop: 7 }}>
            Alimenté par le RAG BCEAO · Documents officiels
          </p>
        </div>
      </div>
    </>
  )
}
