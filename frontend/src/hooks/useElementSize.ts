import { useEffect, useRef, useState } from "react";

/** ResizeObserver wrapper. Returns a ref to attach to an element and the
 *  current content-rect width/height. Used by the mask editor so the Konva
 *  stage stays responsive without locking to a fixed pixel size. */
export function useElementSize<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const ro = new ResizeObserver((entries) => {
      const cr = entries[0]?.contentRect;
      if (cr) setSize({ width: cr.width, height: cr.height });
    });
    ro.observe(node);
    return () => ro.disconnect();
  }, []);

  return [ref, size] as const;
}
