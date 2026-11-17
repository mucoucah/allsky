import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Archive as ArchiveIcon, BarChart3, Calendar, Film, Image as ImageIcon, RefreshCw } from "lucide-react";
import Gallery from "./Gallery";
import Keograms from "./Keograms";
import Videos from "./Videos";
import { DailyLapseSection } from "../sections/archive/DailyLapseSection";
import { GenerateForDateSection } from "../sections/archive/GenerateForDateSection";

const tabs = [
  { id: "images", label: "Images", Icon: ImageIcon },
  { id: "keograms", label: "Keograms & Startrails", Icon: BarChart3 },
  { id: "videos", label: "Timelapses", Icon: Film },
  { id: "dailylapse", label: "Daily-lapse", Icon: Calendar },
  { id: "regenerate", label: "Regenerate night", Icon: RefreshCw },
] as const;

type TabId = (typeof tabs)[number]["id"];

export default function Archive() {
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab");
  const initial = tabs.some((t) => t.id === requested) ? (requested as TabId) : "images";
  const [tab, setTab] = useState<TabId>(initial);

  function select(id: TabId) {
    setTab(id);
    setParams(id === "images" ? {} : { tab: id }, { replace: true });
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <ArchiveIcon size={22} className="text-accent" />
        <h1 className="text-xl font-semibold">Archive</h1>
      </div>
      <div className="flex gap-1 border-b border-bg-raised flex-wrap">
        {tabs.map(({ id, label, Icon }) => (
          <button
            key={id}
            onClick={() => select(id)}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 ${
              tab === id ? "border-accent text-accent" : "border-transparent text-ink-muted"
            }`}
          >
            <Icon size={16} />
            {label}
          </button>
        ))}
      </div>
      {tab === "images" && <Gallery />}
      {tab === "keograms" && <Keograms />}
      {tab === "videos" && <Videos />}
      {tab === "dailylapse" && <div className="max-w-4xl"><DailyLapseSection /></div>}
      {tab === "regenerate" && <div className="max-w-4xl"><GenerateForDateSection /></div>}
    </div>
  );
}
