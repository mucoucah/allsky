import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Send } from "lucide-react";
import { api } from "../../lib/api";

export function ManualSendSection() {
  const [subject, setSubject] = useState("Allsky observation");
  const [body, setBody] = useState("");
  const [snap, setSnap] = useState(true);
  const [tl, setTl] = useState(false);
  const send = useMutation({ mutationFn: api.manualSend });

  return (
    <section className="card">
      <h2 className="text-lg font-semibold flex items-center gap-2 mb-3">
        <Send size={20} /> Send manually
      </h2>
      <div className="flex flex-col gap-2">
        <input
          className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1 text-sm"
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          placeholder="Subject"
        />
        <textarea
          className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1 text-sm resize-y"
          rows={3}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Message body"
        />
        <div className="flex items-center gap-4 text-sm">
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={snap} onChange={(e) => setSnap(e.target.checked)} />
            Include snapshot
          </label>
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={tl} onChange={(e) => setTl(e.target.checked)} />
            Include timelapse
          </label>
          <button
            onClick={() => send.mutate({ subject, body, include_snapshot: snap, include_timelapse: tl })}
            disabled={send.isPending}
            className="ml-auto px-3 py-1.5 rounded-lg bg-accent text-bg-base text-sm font-medium disabled:opacity-50"
          >
            {send.isPending ? "Sending…" : "Send to all channels"}
          </button>
        </div>
        {send.isSuccess && (
          <div className="text-xs text-ok">
            Sent. Results: {JSON.stringify(send.data.results)}
          </div>
        )}
      </div>
    </section>
  );
}
