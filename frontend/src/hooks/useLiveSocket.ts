/** WebSocket hook for the live view.
 *
 *  - Connects once on mount, reconnects with exponential backoff on close.
 *  - Receives binary frames (image/jpeg bytes) and JSON metadata messages,
 *    multiplexed on the same socket.
 *  - Exposes the latest frame as an object URL plus the latest meta payload.
 */
import { useEffect, useRef, useState } from "react";

export interface LiveMeta {
  size?: number;
  mtime?: string;
}

export function useLiveSocket() {
  const [frameUrl, setFrameUrl] = useState<string | null>(null);
  const [meta, setMeta] = useState<LiveMeta | null>(null);
  const [connected, setConnected] = useState(false);
  const previousUrlRef = useRef<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let attempts = 0;
    let stopped = false;
    let timer: number | undefined;

    function connect() {
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const url = `${proto}//${window.location.host}/api/live/ws`;
      const ws = new WebSocket(url);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      ws.onopen = () => {
        attempts = 0;
        setConnected(true);
        // Periodically prod the server so it can detect dead clients quickly.
        const ping = window.setInterval(() => {
          if (ws.readyState === ws.OPEN) ws.send("ping");
        }, 15_000);
        ws.addEventListener("close", () => window.clearInterval(ping));
      };

      ws.onmessage = (ev) => {
        if (typeof ev.data === "string") {
          try {
            const parsed = JSON.parse(ev.data);
            if (parsed.type === "meta") setMeta(parsed.data);
          } catch {
            // ignore non-JSON text frames
          }
          return;
        }
        // Binary frame
        const blob = new Blob([ev.data], { type: "image/jpeg" });
        const next = URL.createObjectURL(blob);
        // Free the previous one (frees ~hundreds of KB per frame).
        if (previousUrlRef.current) URL.revokeObjectURL(previousUrlRef.current);
        previousUrlRef.current = next;
        setFrameUrl(next);
      };

      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        if (stopped) return;
        attempts += 1;
        const delay = Math.min(15_000, 500 * 2 ** Math.min(attempts, 5));
        timer = window.setTimeout(connect, delay);
      };

      ws.onerror = () => ws.close();
    }

    connect();

    return () => {
      stopped = true;
      if (timer) window.clearTimeout(timer);
      wsRef.current?.close();
      if (previousUrlRef.current) URL.revokeObjectURL(previousUrlRef.current);
    };
  }, []);

  return { frameUrl, meta, connected };
}
