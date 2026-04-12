import { useQuery } from "@tanstack/react-query";
import { api, fileUrl } from "../lib/api";

export default function Keograms() {
  const { data: keo } = useQuery({ queryKey: ["keograms"], queryFn: api.keograms });
  const { data: trails } = useQuery({ queryKey: ["startrails"], queryFn: api.startrails });

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Section title="Keograms" items={keo?.items} hrefFor={fileUrl.keogram} />
      <Section title="Startrails" items={trails?.items} hrefFor={fileUrl.startrail} />
    </div>
  );
}

function Section(props: {
  title: string;
  items?: Array<{ name: string; mtime: number }>;
  hrefFor: (n: string) => string;
}) {
  return (
    <section className="card">
      <h2 className="text-lg font-semibold mb-3">{props.title}</h2>
      {props.items?.length ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {props.items.map((it) => (
            <a
              key={it.name}
              href={props.hrefFor(it.name)}
              target="_blank"
              rel="noreferrer"
              className="rounded-xl overflow-hidden border border-bg-raised bg-bg-base"
            >
              <img
                loading="lazy"
                src={props.hrefFor(it.name)}
                alt={it.name}
                className="w-full h-32 object-cover"
              />
              <div className="p-2 text-xs font-mono text-ink-muted truncate">{it.name}</div>
            </a>
          ))}
        </div>
      ) : (
        <div className="text-ink-dim text-sm">none yet</div>
      )}
    </section>
  );
}
