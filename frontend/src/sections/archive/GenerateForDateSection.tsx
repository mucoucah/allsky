import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Calendar } from "lucide-react";
import { api } from "../../lib/api";

export function GenerateForDateSection() {
  const { data: dates } = useQuery({
    queryKey: ["available-dates"],
    queryFn: api.availableDates,
  });
  const [selectedDate, setSelectedDate] = useState("");
  const [kinds, setKinds] = useState<Record<string, boolean>>({
    keogram: true,
    startrails: true,
    timelapse: true,
  });

  const generate = useMutation({
    mutationFn: () => {
      const selected = Object.entries(kinds).filter(([, v]) => v).map(([k]) => k);
      return api.generateForDate(selectedDate, selected);
    },
  });

  return (
    <section className="card">
      <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
        <Calendar size={20} /> Regenerate for past date
      </h2>
      <p className="text-xs text-ink-dim mb-3">
        Re-create keogram, startrails, or timelapse for a specific night. Useful after fixing settings
        or if the automatic end-of-night run failed.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-ink-muted">Date</label>
          <select
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="bg-bg-base border border-bg-raised rounded-lg px-2 py-1.5 text-sm font-mono min-w-[200px]"
          >
            <option value="">Select a date...</option>
            {dates?.dates.map((d: any) => (
              <option key={d.date} value={d.date}>
                {d.date} ({d.image_count} images)
              </option>
            ))}
          </select>
        </div>
        {(["keogram", "startrails", "timelapse"] as const).map((k) => (
          <label key={k} className="flex items-center gap-1.5 text-sm capitalize">
            <input
              type="checkbox"
              checked={kinds[k]}
              onChange={(e) => setKinds({ ...kinds, [k]: e.target.checked })}
            />
            {k}
          </label>
        ))}
        <button
          onClick={() => generate.mutate()}
          disabled={!selectedDate || generate.isPending || !Object.values(kinds).some((v) => v)}
          className="px-3 py-1.5 rounded-lg bg-accent text-bg-base text-sm font-medium disabled:opacity-50"
        >
          {generate.isPending ? "Generating (can take minutes)..." : "Generate"}
        </button>
      </div>
      {generate.data && (
        <div className={`mt-3 p-2 rounded-lg text-xs ${generate.data.ok ? "bg-ok/10 text-ok" : "bg-err/10 text-err"}`}>
          {generate.data.ok ? "Completed successfully." : generate.data.error || "Failed."}
          {generate.data.output && (
            <pre className="mt-2 text-ink-muted whitespace-pre-wrap max-h-40 overflow-auto">
              {generate.data.output}
            </pre>
          )}
        </div>
      )}
    </section>
  );
}
