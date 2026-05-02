import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./routes/Dashboard";
import Gallery from "./routes/Gallery";
import Settings from "./routes/Settings";
import Media from "./routes/Media";
import ImageTools from "./routes/ImageTools";
import SkyMonitor from "./routes/SkyMonitor";
import Alerts from "./routes/Alerts";
import System from "./routes/System";
import Setup from "./routes/Setup";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="gallery" element={<Gallery />} />
        <Route path="settings" element={<Settings />} />
        <Route path="media" element={<Media />} />
        <Route path="image-tools" element={<ImageTools />} />
        <Route path="sky-monitor" element={<SkyMonitor />} />
        <Route path="alerts" element={<Alerts />} />
        <Route path="system" element={<System />} />
        <Route path="setup" element={<Setup />} />

        {/* Redirects from old routes */}
        <Route path="keograms" element={<Navigate to="/media" replace />} />
        <Route path="videos" element={<Navigate to="/media" replace />} />
        <Route path="mask" element={<Navigate to="/image-tools" replace />} />
        <Route path="overlay" element={<Navigate to="/image-tools" replace />} />
        <Route path="notifications" element={<Navigate to="/sky-monitor" replace />} />
        <Route path="maintenance" element={<Navigate to="/system" replace />} />
      </Route>
    </Routes>
  );
}
