'use client';

import { useEffect, useRef, useState } from 'react';
import { AI_ROLES, DEFAULT_ROLE_ID, getRoleById, type AIRole } from '@/lib/ai-roles';
import { AI_MODELS, type AIModel } from '@/lib/ai-models';

// ── Types ─────────────────────────────────────────────────────────────────────

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  model?: string;
  error?: boolean;
}

// ── Role selector ─────────────────────────────────────────────────────────────

function RoleSelector({
  selected,
  onChange,
}: {
  selected: string;
  onChange: (id: string) => void;
}) {
  const deptColour: Record<string, string> = {
    engineering: 'border-science text-science',
    command:     'border-command text-command',
    operations:  'border-operations text-operations',
    science:     'border-medical text-medical',
  };

  return (
    <div className="flex flex-wrap gap-2">
      {AI_ROLES.map((r) => {
        const active = r.id === selected;
        const colour = deptColour[r.department] ?? 'border-edge text-lcars-muted';
        return (
          <button
            key={r.id}
            onClick={() => onChange(r.id)}
            className={`rounded-lcars border px-3 py-1.5 text-xs font-semibold transition-colors ${
              active
                ? `${colour} bg-white/5`
                : 'border-edge bg-space/40 text-lcars-muted hover:border-edge/80'
            }`}
          >
            {r.label}
          </button>
        );
      })}
    </div>
  );
}

// ── Model selector ────────────────────────────────────────────────────────────

function ModelSelector({
  selected,
  onChange,
}: {
  selected: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {AI_MODELS.map((m) => (
        <button
          key={m.id}
          onClick={() => m.available && onChange(m.id)}
          disabled={!m.available}
          title={m.description}
          className={`rounded-lcars border px-3 py-1 text-[11px] font-mono transition-colors ${
            selected === m.id
              ? 'border-command bg-command/20 text-command'
              : m.available
              ? 'border-edge bg-space/40 text-lcars-muted hover:border-command/40'
              : 'border-edge/40 bg-space/20 text-lcars-muted/40 cursor-not-allowed'
          }`}
        >
          {m.label}
        </button>
      ))}
    </div>
  );
}

// ── Message bubble ────────────────────────────────────────────────────────────

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] rounded-lcars border px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
          isUser
            ? 'border-command/40 bg-command/10 text-lcars-text'
            : msg.error
            ? 'border-operations/40 bg-operations/10 text-operations'
            : 'border-edge bg-panel/60 text-lcars-text/90'
        }`}
      >
        {!isUser && (
          <p className="mb-1.5 text-[10px] uppercase tracking-[0.2em] text-lcars-muted">
            {msg.model ?? 'GLM 5.2'}
          </p>
        )}
        {msg.content}
      </div>
    </div>
  );
}

// ── Loading indicator ─────────────────────────────────────────────────────────

function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="rounded-lcars border border-edge bg-panel/60 px-4 py-3">
        <div className="flex gap-1.5 items-center h-4">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="h-1.5 w-1.5 rounded-full bg-command animate-pulse"
              style={{ animationDelay: `${i * 150}ms` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AIConsolePage() {
  const [messages, setMessages]         = useState<Message[]>([]);
  const [input, setInput]               = useState('');
  const [selectedRole, setSelectedRole] = useState(DEFAULT_ROLE_ID);
  const [selectedModel, setSelectedModel] = useState('glm-5.2');
  const [systemPrompt, setSystemPrompt] = useState(getRoleById(DEFAULT_ROLE_ID).systemPrompt);
  const [editingPrompt, setEditingPrompt] = useState(false);
  const [loading, setLoading]           = useState(false);
  const [streamBuffer, setStreamBuffer] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef  = useRef<HTMLTextAreaElement>(null);

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamBuffer]);

  // Update system prompt when role changes — but don't override user edits
  function handleRoleChange(id: string) {
    setSelectedRole(id);
    setSystemPrompt(getRoleById(id).systemPrompt);
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);
    setStreamBuffer('');

    // Build message history (exclude errors from context)
    const history = [...messages, userMsg]
      .filter((m) => !m.error)
      .map(({ role, content }) => ({ role, content }));

    try {
      const res = await fetch('/api/ai/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: history,
          model: selectedModel,
          role: selectedRole,
          stream: true,
          systemPrompt,
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({ error: 'Request failed' }));
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: errData.error ?? 'Request failed',
            error: true,
          },
        ]);
        return;
      }

      // Handle SSE stream
      const reader = res.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let accumulated = '';
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const payload = line.slice(6);
          if (payload === '[DONE]') break;
          try {
            const chunk = JSON.parse(payload);
            if (chunk.error) throw new Error(chunk.error);
            if (chunk.token) {
              accumulated += chunk.token;
              setStreamBuffer(accumulated);
            }
          } catch (e) {
            if (e instanceof Error && e.message !== 'JSON parse') {
              throw e;
            }
          }
        }
      }

      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: accumulated || '(No response)',
          model: selectedModel,
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content:
            err instanceof Error
              ? err.message
              : 'Connection to Ollama Cloud failed.',
          error: true,
        },
      ]);
    } finally {
      setLoading(false);
      setStreamBuffer('');
      inputRef.current?.focus();
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function clearConversation() {
    setMessages([]);
    setStreamBuffer('');
  }

  return (
    <div className="flex flex-col gap-3 h-[calc(100vh-12rem)]">

      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-2 flex-shrink-0">
        <div>
          <p className="text-[10px] uppercase tracking-[0.3em] text-lcars-muted">AI Console</p>
          <h1 className="font-lcars text-xl font-bold text-lcars-text">Command Deck AI</h1>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[10px] uppercase tracking-[0.2em] text-status">● Ollama Cloud</span>
          {messages.length > 0 && (
            <button
              onClick={clearConversation}
              className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted hover:text-operations transition-colors"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* ── Config strip ── */}
      <div className="flex-shrink-0 rounded-lcars border border-edge bg-panel/40 p-3 flex flex-col gap-3">

        {/* Role + model row */}
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-col gap-1.5">
            <p className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted">Role preset</p>
            <RoleSelector selected={selectedRole} onChange={handleRoleChange} />
          </div>
          <div className="flex flex-col gap-1.5">
            <p className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted">Model</p>
            <ModelSelector selected={selectedModel} onChange={setSelectedModel} />
          </div>
        </div>

        {/* System prompt — editable */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <p className="text-[10px] uppercase tracking-[0.2em] text-lcars-muted">
              System prompt
            </p>
            <button
              onClick={() => setEditingPrompt((v) => !v)}
              className="text-[10px] uppercase tracking-[0.2em] text-command hover:opacity-70 transition-opacity"
            >
              {editingPrompt ? 'Done' : 'Edit'}
            </button>
          </div>
          {editingPrompt ? (
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              rows={5}
              className="w-full rounded-lcars border border-command/40 bg-space px-3 py-2 text-xs text-lcars-text/90 placeholder:text-lcars-muted focus:border-command focus:outline-none resize-y font-mono"
            />
          ) : (
            <p className="text-xs text-lcars-muted/70 line-clamp-2 italic">
              {systemPrompt.split('\n')[0]}
            </p>
          )}
        </div>
      </div>

      {/* ── Message history ── */}
      <div className="flex-1 overflow-y-auto rounded-lcars border border-edge bg-space/60 p-3 flex flex-col gap-3 min-h-0">
        {messages.length === 0 && !loading && (
          <div className="flex flex-1 items-center justify-center">
            <p className="text-xs text-lcars-muted text-center">
              Select a role, adjust the system prompt if needed, then send a message.
              <br />
              <span className="text-[10px] opacity-60">Shift+Enter for new line · Enter to send</span>
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}

        {/* Live stream buffer */}
        {loading && streamBuffer && (
          <div className="flex justify-start">
            <div className="max-w-[85%] rounded-lcars border border-edge bg-panel/60 px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap text-lcars-text/90">
              <p className="mb-1.5 text-[10px] uppercase tracking-[0.2em] text-lcars-muted">
                {selectedModel}
              </p>
              {streamBuffer}
              <span className="inline-block w-1.5 h-3.5 bg-command animate-pulse ml-0.5 align-middle" />
            </div>
          </div>
        )}

        {loading && !streamBuffer && <TypingIndicator />}

        <div ref={bottomRef} />
      </div>

      {/* ── Input area ── */}
      <div className="flex-shrink-0 flex gap-2 items-end">
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={2}
          placeholder="Message GLM 5.2…"
          disabled={loading}
          className="flex-1 rounded-lcars border border-edge bg-space px-3 py-2 text-sm text-lcars-text placeholder:text-lcars-muted focus:border-command focus:outline-none resize-none disabled:opacity-50"
        />
        <button
          onClick={handleSend}
          disabled={loading || !input.trim()}
          className="rounded-lcars bg-command px-4 py-2 font-lcars text-sm font-bold uppercase tracking-[0.15em] text-space transition-opacity hover:opacity-80 disabled:opacity-40 self-stretch flex items-center"
        >
          {loading ? '…' : 'Send'}
        </button>
      </div>

    </div>
  );
}
