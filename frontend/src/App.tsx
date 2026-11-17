import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Live from "./routes/Live";
import Tonight from "./routes/Tonight";
import Archive from "./routes/Archive";
import Camera from "./routes/Camera";
import System from "./routes/System";
import Extras from "./routes/Extras";
import Setup from "./routes/Setup";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Live />} />
        <Route path="tonight" element={<Tonight />} />
        <Route path="archive" element={<Archive />} />
        <Route path="camera" element={<Camera />} />
        <Route path="system" element={<System />} />
        <Route path="extras" element={<Extras />} />
        <Route path="setup" element={<Setup />} />

        <Route path="gallery" element={<Navigate to="/archive" replace />} />
        <Route path="media" element={<Navigate to="/archive" replace />} />
        <Route path="keograms" element={<Navigate to="/archive?tab=keograms" replace />} />
        <Route path="videos" element={<Navigate to="/archive?tab=videos" replace />} />
        <Route path="settings" element={<Navigate to="/camera" replace />} />
        <Route path="image-tools" element={<Navigate to="/camera?tab=mask" replace />} />
        <Route path="mask" element={<Navigate to="/camera?tab=mask" replace />} />
        <Route path="overlay" element={<Navigate to="/camera" replace />} />
        <Route path="sky-monitor" element={<Navigate to="/tonight" replace />} />
        <Route path="notifications" element={<Navigate to="/extras" replace />} />
        <Route path="alerts" element={<Navigate to="/extras#alerts" replace />} />
        <Route path="maintenance" element={<Navigate to="/system" replace />} />
      </Route>
    </Routes>
  );
}
