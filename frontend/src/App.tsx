import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./routes/Dashboard";
import Gallery from "./routes/Gallery";
import Settings from "./routes/Settings";
import MaskEditor from "./routes/MaskEditor";
import Keograms from "./routes/Keograms";
import Alerts from "./routes/Alerts";
import Notifications from "./routes/Notifications";
import System from "./routes/System";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="gallery" element={<Gallery />} />
        <Route path="settings" element={<Settings />} />
        <Route path="mask" element={<MaskEditor />} />
        <Route path="keograms" element={<Keograms />} />
        <Route path="alerts" element={<Alerts />} />
        <Route path="notifications" element={<Notifications />} />
        <Route path="system" element={<System />} />
      </Route>
    </Routes>
  );
}
