"""Chat UI route.

GET /   — redirect to /ui
GET /ui — serve the single-page chat interface
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter(tags=["ui"])

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>VIKI — Talk to your inbox</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background: #0f1117;
      color: #e2e8f0;
      font-family: system-ui, -apple-system, sans-serif;
      display: flex;
      flex-direction: column;
      height: 100dvh;
    }

    header {
      padding: 12px 20px;
      background: #1a1d2e;
      border-bottom: 1px solid #2d3147;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-shrink: 0;
    }

    header h1 { font-size: 1.1rem; font-weight: 600; color: #818cf8; }

    #sync-btn {
      background: #1e293b;
      border: 1px solid #334155;
      color: #94a3b8;
      padding: 6px 14px;
      border-radius: 6px;
      cursor: pointer;
      font-size: 0.8rem;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: background 0.15s;
    }
    #sync-btn:hover { background: #273549; }
    #sync-btn:disabled { opacity: 0.5; cursor: not-allowed; }

    #sync-status { font-size: 0.75rem; color: #64748b; min-width: 120px; text-align: right; }

    #messages {
      flex: 1;
      overflow-y: auto;
      padding: 20px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    .msg { max-width: 780px; width: 100%; }
    .msg.user { align-self: flex-end; }
    .msg.assistant { align-self: flex-start; }

    .bubble {
      padding: 12px 16px;
      border-radius: 12px;
      line-height: 1.6;
      font-size: 0.93rem;
      white-space: pre-wrap;
      word-break: break-word;
    }

    .msg.user .bubble {
      background: #312e81;
      color: #e0e7ff;
      border-bottom-right-radius: 4px;
    }
    .msg.assistant .bubble {
      background: #1e293b;
      color: #e2e8f0;
      border-bottom-left-radius: 4px;
    }
    .msg.assistant.error .bubble {
      background: #450a0a;
      color: #fca5a5;
    }

    .sources-toggle {
      margin-top: 8px;
      font-size: 0.75rem;
      color: #818cf8;
      cursor: pointer;
      user-select: none;
    }
    .sources-toggle:hover { color: #a5b4fc; }

    .sources-list {
      margin-top: 4px;
      padding: 8px 12px;
      background: #0f172a;
      border-radius: 6px;
      font-size: 0.75rem;
      color: #94a3b8;
      display: none;
    }
    .sources-list.open { display: block; }
    .sources-list li { list-style: disc; margin-left: 16px; margin-top: 2px; word-break: break-all; }

    .thinking {
      display: flex;
      gap: 4px;
      padding: 14px 16px;
      background: #1e293b;
      border-radius: 12px;
      border-bottom-left-radius: 4px;
      width: fit-content;
    }
    .dot {
      width: 7px; height: 7px;
      border-radius: 50%;
      background: #818cf8;
      animation: bounce 1.2s ease-in-out infinite;
    }
    .dot:nth-child(2) { animation-delay: 0.2s; }
    .dot:nth-child(3) { animation-delay: 0.4s; }
    @keyframes bounce {
      0%, 80%, 100% { transform: translateY(0); }
      40% { transform: translateY(-6px); }
    }

    #input-area {
      padding: 16px 20px;
      background: #1a1d2e;
      border-top: 1px solid #2d3147;
      display: flex;
      gap: 10px;
      flex-shrink: 0;
    }

    #query-input {
      flex: 1;
      background: #0f1117;
      border: 1px solid #334155;
      border-radius: 8px;
      color: #e2e8f0;
      padding: 10px 14px;
      font-size: 0.93rem;
      outline: none;
      resize: none;
      height: 44px;
      max-height: 140px;
      overflow-y: auto;
      line-height: 1.5;
    }
    #query-input:focus { border-color: #4f46e5; }
    #query-input::placeholder { color: #475569; }

    #send-btn {
      background: #4f46e5;
      border: none;
      border-radius: 8px;
      color: white;
      width: 44px;
      height: 44px;
      cursor: pointer;
      font-size: 1.1rem;
      flex-shrink: 0;
      transition: background 0.15s;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    #send-btn:hover { background: #4338ca; }
    #send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
  </style>
</head>
<body>
  <header>
    <h1>VIKI</h1>
    <div style="display:flex;align-items:center;gap:12px">
      <span id="sync-status"></span>
      <button id="sync-btn">&#8635; Sync Gmail</button>
    </div>
  </header>

  <div id="messages">
    <div class="msg assistant">
      <div class="bubble">Hi, I'm VIKI. Ask me anything about your inbox and notes.</div>
    </div>
  </div>

  <div id="input-area">
    <textarea id="query-input" placeholder="Ask a question…" rows="1"></textarea>
    <button id="send-btn" aria-label="Send">&#9650;</button>
  </div>

  <script>
    const messagesEl = document.getElementById('messages');
    const inputEl    = document.getElementById('query-input');
    const sendBtn    = document.getElementById('send-btn');
    const syncBtn    = document.getElementById('sync-btn');
    const syncStatus = document.getElementById('sync-status');

    inputEl.addEventListener('input', () => {
      inputEl.style.height = 'auto';
      inputEl.style.height = Math.min(inputEl.scrollHeight, 140) + 'px';
    });

    inputEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    });
    sendBtn.addEventListener('click', handleSend);

    function appendMessage(role, text, sources, isError) {
      const wrapper = document.createElement('div');
      wrapper.className = 'msg ' + role + (isError ? ' error' : '');

      const bubble = document.createElement('div');
      bubble.className = 'bubble';
      bubble.textContent = text;
      wrapper.appendChild(bubble);

      if (role === 'assistant' && sources && sources.length > 0) {
        const toggle = document.createElement('div');
        toggle.className = 'sources-toggle';
        const label = () => sources.length + ' source' + (sources.length > 1 ? 's' : '');
        toggle.textContent = '▶ ' + label();

        const list = document.createElement('ul');
        list.className = 'sources-list';
        sources.forEach(src => {
          const li = document.createElement('li');
          li.textContent = src;
          list.appendChild(li);
        });

        toggle.addEventListener('click', () => {
          list.classList.toggle('open');
          toggle.textContent = (list.classList.contains('open') ? '▼ ' : '▶ ') + label();
        });

        wrapper.appendChild(toggle);
        wrapper.appendChild(list);
      }

      messagesEl.appendChild(wrapper);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function showThinking() {
      const wrapper = document.createElement('div');
      wrapper.className = 'msg assistant';
      wrapper.id = 'thinking-indicator';
      const thinking = document.createElement('div');
      thinking.className = 'thinking';
      for (let i = 0; i < 3; i++) {
        const d = document.createElement('div');
        d.className = 'dot';
        thinking.appendChild(d);
      }
      wrapper.appendChild(thinking);
      messagesEl.appendChild(wrapper);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function removeThinking() {
      const el = document.getElementById('thinking-indicator');
      if (el) el.remove();
    }

    async function handleSend() {
      const query = inputEl.value.trim();
      if (!query) return;

      inputEl.value = '';
      inputEl.style.height = '44px';
      setInputDisabled(true);

      appendMessage('user', query, null, false);
      showThinking();

      try {
        const resp = await fetch('/ask', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query, tenant_id: 'default', limit: 10 }),
        });
        removeThinking();

        if (!resp.ok) {
          const err = await resp.json().catch(() => ({ detail: resp.statusText }));
          appendMessage('assistant', 'Error: ' + (err.detail || JSON.stringify(err)), null, true);
        } else {
          const data = await resp.json();
          appendMessage('assistant', data.answer, data.sources, false);
        }
      } catch (e) {
        removeThinking();
        appendMessage('assistant', 'Network error: ' + e.message, null, true);
      } finally {
        setInputDisabled(false);
        inputEl.focus();
      }
    }

    syncBtn.addEventListener('click', async () => {
      syncBtn.disabled = true;
      syncStatus.textContent = 'Syncing…';

      try {
        const resp = await fetch('/ingest/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ source: 'gmail' }),
        });

        if (!resp.ok) {
          const err = await resp.json().catch(() => ({ detail: resp.statusText }));
          syncStatus.textContent = 'Sync failed: ' + (err.detail || resp.statusText);
        } else {
          const data = await resp.json();
          syncStatus.textContent = 'Synced — ' + data.fetched + ' fetched, ' + data.ingested + ' stored';
        }
      } catch (e) {
        syncStatus.textContent = 'Error: ' + e.message;
      } finally {
        syncBtn.disabled = false;
        setTimeout(() => { syncStatus.textContent = ''; }, 8000);
      }
    });

    function setInputDisabled(val) {
      inputEl.disabled = val;
      sendBtn.disabled = val;
    }
  </script>
</body>
</html>"""


@router.get("/", include_in_schema=False)
async def root_redirect() -> RedirectResponse:
    return RedirectResponse(url="/ui")


@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
async def ui() -> str:
    return _HTML
