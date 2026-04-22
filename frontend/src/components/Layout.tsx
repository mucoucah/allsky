import { NavLink, Outlet } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  LayoutDashboard, Image as ImageIcon, Settings as SettingsIcon,
  Eraser, BarChart3, Film, Bell, Cpu, Radar, Wrench, Package, Layers,
} from "lucide-react";
import { api } from "../lib/api";
import { LogConsole } from "./LogConsole";

const links = [
  { to: "/",               label: "Dashboard",     Icon: LayoutDashboard },
  { to: "/gallery",        label: "Gallery",        Icon: ImageIcon },
  { to: "/settings",       label: "Settings",       Icon: SettingsIcon },
  { to: "/mask",           label: "Mask",           Icon: Eraser },
  { to: "/overlay",        label: "Overlay",        Icon: Layers },
  { to: "/keograms",       label: "Keograms",       Icon: BarChart3 },
  { to: "/videos",         label: "Videos",         Icon: Film },
  { to: "/alerts",         label: "Alerts",         Icon: Bell },
  { to: "/notifications",  label: "Notifications",  Icon: Radar },
  { to: "/setup",          label: "Setup",          Icon: Wrench },
  { to: "/system",         label: "System",         Icon: Cpu },
  { to: "/maintenance",    label: "Maintenance",    Icon: Package },
];

export default function Layout() {
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    staleTime: 300_000,
  });

  return (
    <div className="min-h-full flex flex-col">
      <header className="border-b border-bg-raised bg-bg-panel/80 backdrop-blur sticky top-0 z-20">
        <div className="px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-full bg-accent/20 border border-accent/40" />
            <div className="font-semibold tracking-tight">Allsky</div>
            <div className="text-ink-dim text-xs hidden sm:block">
              v{health?.version ?? "..."}
            </div>
          </div>
        </div>
      </header>

      <div className="flex-1 flex md:flex-row flex-col">
        {/* Sidebar (md+) */}
        <nav className="hidden md:flex flex-col gap-1 p-3 w-52 border-r border-bg-raised">
          {links.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `nav-link flex items-center gap-2 ${isActive ? "active" : ""}`
              }
            >
              <Icon size={18} />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Main */}
        <main className="flex-1 p-4 md:p-6 max-w-screen-2xl w-full mx-auto pb-24 md:pb-6">
          <Outlet />
        </main>
      </div>

      {/* Bottom nav (mobile) — horizontally scrollable */}
      <nav className="md:hidden fixed bottom-0 inset-x-0 z-30 bg-bg-panel/95 border-t border-bg-raised overflow-x-auto scrollbar-hide">
        <div className="flex items-center gap-1 px-2 py-2 min-w-max">
          {links.map(({ to, label, Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `flex flex-col items-center gap-0.5 px-3 py-1 rounded-lg shrink-0 ${
                  isActive ? "text-accent" : "text-ink-muted"
                }`
              }
            >
              <Icon size={20} />
              <span className="text-[10px]">{label}</span>
            </NavLink>
          ))}
        </div>
      </nav>

      {/* Floating log console — available on every page */}
      <LogConsole />
    </div>
  );
}
