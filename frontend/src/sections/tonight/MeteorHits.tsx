import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type MeteorHit } from "../../lib/api";

export function MeteorHits() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["meteor-hits"],
    queryFn: api.meteorHits,
    refetchInterval: 30_000,
  });
  const [open, setOpen] = useState<MeteorHit | null>(null);
  const hits = data?.hits ?? [];

  return (
    <section className="card flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Meteor hits</h2>
        <span className="text-xs text-ink-dim">{data ? `${data.total} saved` : ""}</span>
      </div>
      <p className="text-xs text-ink-dim">
        Read-only. Each hit is the crop around the streak. Open one for the full frame.
        Files live under html/allsky/meteors/.
      </p>
      {isLoading && <div className="text-sm text-ink-dim">Loading hits…</div>}
      {isError && <div className="text-sm text-err">Could not load meteor hits.</div>}
      {!isLoading && hits.length === 0 && (
        <div className="text-sm text-ink-dim">No meteor hits saved yet.</div>
      )}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {hits.map((hit) => (
          <button
            key={`${hit.date}/${hit.id}`}
            type="button"
            onClick={() => setOpen(hit)}
            className="text-left rounded-xl border border-bg-raised overflow-hidden bg-bg-base hover:border-accent/50"
          >
            {hit.crop_url ? (
              <img src={hit.crop_url} alt="" className="w-full aspect-video object-cover bg-black" />
            ) : (
              <div className="w-full aspect-video bg-black" />
            )}
            <div className="p-2">
              <div className="text-xs font-mono truncate">{hit.time ?? hit.id}</div>
              <div className="text-[10px] text-ink-dim">
                {hit.meteor_count ?? "?"} streak{(hit.meteor_count ?? 0) === 1 ? "" : "s"}
              </div>
            </div>
          </button>
        ))}
      </div>
      {open && (
        <div
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
          onClick={() => setOpen(null)}
        >
          <div className="max-w-5xl w-full" onClick={(e) => e.stopPropagation()}>
            {open.frame_url ? (
              <img src={open.frame_url} alt="Full meteor frame" className="w-full max-h-[80vh] object-contain bg-black" />
            ) : (
              <div className="text-ink-dim">No full frame saved for this hit.</div>
            )}
            <div className="mt-2 text-sm text-white/80 flex flex-wrap gap-3">
              <span className="font-mono">{open.time ?? open.id}</span>
              <span>{open.date}</span>
              {open.frame_url && (
                <a className="text-accent underline" href={open.frame_url} target="_blank" rel="noreferrer">
                  Open full frame
                </a>
              )}
              <button type="button" className="ml-auto text-white/70" onClick={() => setOpen(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
