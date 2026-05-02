import { useState } from "react";
import { BarChart3, Film, Calendar } from "lucide-react";
import Keograms from "./Keograms";
import Videos from "./Videos";
import { DailyLapseSection } from "./Maintenance";

const tabs = [
  { id: "keograms", label: "Keograms & Startrails", Icon: BarChart3 },
  { id: "videos", label: "Videos", Icon: Film },
  { id: "dailylapse", label: "Daily-Lapse", Icon: Calendar },
] as const;

type TabId = (typeof tabs)[number]["id"];

export default function Media() {
  const [tab, setTab] = useState<TabId>("keograms");

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3 flex-wrap">
        <Film size={22} className="text-accent" />
        <h1 className="text-xl font-semibold">Media</h1>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-bg-raised">
        {tabs.map(({ id, label, Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              tab === id
                ? "border-accent text-accent"
                : "border-transparent text-ink-muted hover:text-ink"
            }`}
          >
            <Icon size={16} />
            {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === "keograms" && <Keograms />}
      {tab === "videos" && <Videos />}
      {tab === "dailylapse" && (
        <div className="max-w-4xl">
          <DailyLapseSection />
        </div>
      )}
    </div>
  );
}
