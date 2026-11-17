import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

/** True when the Pi only captures and this PC does the processing. */
export function useCaptureOnly(): boolean {
  const { data } = useQuery({
    queryKey: ["offload"],
    queryFn: api.offload,
    staleTime: 30_000,
  });
  return data?.mode === "capture-only";
}
