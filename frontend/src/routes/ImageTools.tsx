import { useState } from "react";
import { Eraser, Layers } from "lucide-react";
import MaskEditor from "./MaskEditor";
import OverlayEditor from "./OverlayEditor";

const tabs = [
  { id: "mask", label: "Mask Editor", Icon: Eraser },
  { id: "overlay", label: "Overlay Editor", Icon: Layers },
] as const;

type TabId = (typeof tabs)[number]["id"];

export default function ImageTools() {
  const [tab, setTab] = useState<TabId>("mask");

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3 flex-wrap">
        <Layers size={22} className="text-accent" />
        <h1 className="text-xl font-semibold">Image Tools</h1>
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
      {tab === "mask" && <MaskEditor />}
      {tab === "overlay" && <OverlayEditor />}
    </div>
  );
}
