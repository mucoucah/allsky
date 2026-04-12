import { useEffect, useRef, useState } from "react";
import { Terminal, X, Minus } from "lucide-react";

/** Floating log console — connects to /api/logs/stream via WebSocket
 *  and shows live backend output. Toggle with the terminal icon in the
 *  bottom-right corner. Available on every page. */
export function LogConsole() {
  const [open, setOpen] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [lines, setLines] = useState<string[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!open) return;

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${window.location.host}/api/logs/stream`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      setLines((prev) => {
        const next = [...prev, ev.data];
        // Keep last 500 lines to avoid memory bloat.
        return next.length > 500 ? next.slice(-500) : next;
      });
    };

    ws.onclose = () => {
      setLines((prev) => [...prev, "--- disconnected ---"]);
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [open]);

  // Auto-scroll to bottom on new lines.
  useEffect(() => {
    if (bottomRef.current && !minimized) {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [lines, minimized]);

  // Floating trigger button (always visible).
  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-20 md:bottom-4 right-4 z-40 p-2.5 rounded-full bg-bg-panel border border-bg-raised shadow-lg text-ink-muted hover:text-accent transition-colors"
        title="Open log console"
      >
        <Terminal size={20} />
      </button>
    );
  }

  return (
    <div
      className={`fixed z-40 bg-bg-panel border border-bg-raised rounded-t-xl shadow-2xl transition-all ${
        minimized
          ? "bottom-0 right-4 w-72 h-10"
          : "bottom-0 right-0 left-0 md:left-auto md:w-[600px] h-72"
      }`}
    >
      {/* Title bar */}
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-bg-raised bg-bg-raised/50 rounded-t-xl cursor-pointer"
        onClick={() => setMinimized(!minimized)}
      >
        <div className="flex items-center gap-2 text-sm text-ink-muted">
          <Terminal size={14} />
          <span>Log console</span>
          <span className="text-[10px] text-ink-dim">{lines.length} lines</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={(e) => { e.stopPropagation(); setMinimized(!minimized); }}
            className="p-1 rounded hover:bg-bg-base text-ink-dim"
          >
            <Minus size={14} />
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); setOpen(false); setLines([]); }}
            className="p-1 rounded hover:bg-bg-base text-ink-dim"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Log output */}
      {!minimized && (
        <div className="overflow-auto h-[calc(100%-2.25rem)] p-2 font-mono text-[11px] leading-relaxed text-ink-muted">
          {lines.length === 0 && (
            <div className="text-ink-dim">connecting...</div>
          )}
          {lines.map((line, i) => (
            <div key={i} className={lineColor(line)}>
              {line}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}

function lineColor(line: string): string {
  if (line.includes("ERROR") || line.includes("error")) return "text-err";
  if (line.includes("WARNING") || line.includes("warning")) return "text-warn";
  if (line.includes("INFO")) return "text-ink-muted";
  return "text-ink-dim";
}
