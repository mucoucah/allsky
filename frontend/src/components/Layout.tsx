import { useState, useCallback, useEffect } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  LayoutDashboard, Image as ImageIcon, Settings as SettingsIcon,
  Film, Bell, Cpu, Radar, Layers,
} from "lucide-react";
import { api } from "../lib/api";
import { LogConsole } from "./LogConsole";

const links = [
  { to: "/",               label: "Dashboard",     Icon: LayoutDashboard },
  { to: "/gallery",        label: "Gallery",        Icon: ImageIcon },
  { to: "/media",          label: "Media",          Icon: Film },
  { to: "/settings",       label: "Settings",       Icon: SettingsIcon },
  { to: "/image-tools",    label: "Image Tools",    Icon: Layers },
  { to: "/sky-monitor",    label: "Sky Monitor",    Icon: Radar },
  { to: "/alerts",         label: "Alerts",         Icon: Bell },
  { to: "/system",         label: "System",         Icon: Cpu },
];

export default function Layout() {
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();

  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    staleTime: 300_000,
  });

  // Close menu on navigation.
  useEffect(() => { setMenuOpen(false); }, [location.pathname]);

  const toggle = useCallback(() => setMenuOpen((v) => !v), []);

  return (
    <div className="min-h-full flex flex-col">
      <header className="border-b border-bg-raised bg-bg-panel/80 backdrop-blur sticky top-0 z-40">
        <div className="px-4 py-3 flex items-center justify-between">
          <button
            onClick={toggle}
            className="md:pointer-events-none flex items-center gap-2"
          >
            <div className={`w-7 h-7 rounded-full border transition-colors ${menuOpen ? "bg-accent/40 border-accent" : "bg-accent/20 border-accent/40"}`} />
            <div className="font-semibold tracking-tight">Allsky</div>
          </button>
          <div className="text-ink-dim text-xs">
            v{health?.version ?? "..."}
          </div>
        </div>
      </header>

      <div className="flex-1 flex md:flex-row flex-col">
        {/* Sidebar (md+) — always visible */}
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
        <main className="flex-1 p-4 md:p-6 max-w-screen-2xl w-full mx-auto">
          <Outlet />
        </main>
      </div>

      {/* Mobile dropdown menu — toggled by logo tap */}
      {menuOpen && (
        <>
          <div
            className="md:hidden fixed inset-0 z-30 bg-black/50"
            onClick={() => setMenuOpen(false)}
          />
          <nav className="md:hidden fixed top-[57px] left-0 right-0 z-40 bg-bg-panel border-b border-bg-raised shadow-lg animate-menu-in">
            <div className="grid grid-cols-3 gap-1 p-3">
              {links.map(({ to, label, Icon }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={to === "/"}
                  className={({ isActive }) =>
                    `flex flex-col items-center gap-1 py-3 px-2 rounded-xl transition-colors ${
                      isActive
                        ? "bg-accent/15 text-accent"
                        : "text-ink-muted active:bg-bg-raised"
                    }`
                  }
                >
                  <Icon size={22} />
                  <span className="text-[11px] font-medium">{label}</span>
                </NavLink>
              ))}
            </div>
          </nav>
        </>
      )}

      {/* Floating log console — available on every page */}
      <LogConsole />
    </div>
  );
}
