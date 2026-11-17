import { useEffect, useState } from "react";

/** Poll interval that pauses while the browser tab is hidden. */
export function usePollInterval(ms: number): number | false {
  const [visible, setVisible] = useState(
    () => typeof document === "undefined" || document.visibilityState === "visible",
  );
  useEffect(() => {
    const onChange = () => setVisible(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", onChange);
    return () => document.removeEventListener("visibilitychange", onChange);
  }, []);
  return visible ? ms : false;
}
