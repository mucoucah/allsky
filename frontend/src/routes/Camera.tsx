import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Camera as CameraIcon, Eraser, SlidersHorizontal } from "lucide-react";
import Settings from "./Settings";
import MaskEditor from "./MaskEditor";
import { CaptureSettings } from "../components/OffloadPanel";

const tabs = [
  { id: "settings", label: "Camera settings", Icon: SlidersHorizontal },
  { id: "capture", label: "Capture", Icon: CameraIcon },
  { id: "mask", label: "Mask", Icon: Eraser },
] as const;

type TabId = (typeof tabs)[number]["id"];

export default function Camera() {
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab");
  const initial = tabs.some((t) => t.id === requested) ? (requested as TabId) : "settings";
  const [tab, setTab] = useState<TabId>(initial);

  function select(id: TabId) {
    setTab(id);
    setParams(id === "settings" ? {} : { tab: id }, { replace: true });
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <CameraIcon size={22} className="text-accent" />
        <h1 className="text-xl font-semibold">Camera</h1>
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
      {tab === "settings" && <Settings />}
      {tab === "capture" && <div className="max-w-4xl"><CaptureSettings /></div>}
      {tab === "mask" && <MaskEditor />}
    </div>
  );
}
