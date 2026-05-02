import { Radar } from "lucide-react";
import {
  MeteorSection,
  FocusSection,
  RainSection,
  AdsbSection,
  SatelliteSection,
} from "./Notifications";

export default function SkyMonitor() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3 flex-wrap">
        <Radar size={22} className="text-accent" />
        <h1 className="text-xl font-semibold">Sky Monitor</h1>
      </div>
      <p className="text-sm text-ink-dim -mt-2">
        Detection and tracking features — configure what to watch for in your sky.
        Alerts are sent via the channels configured in the Alerts page.
      </p>
      <MeteorSection />
      <FocusSection />
      <RainSection />
      <AdsbSection />
      <SatelliteSection />
    </div>
  );
}
