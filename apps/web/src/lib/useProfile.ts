import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { components } from "../api/schema";
import { stringifyError } from "./format";

export type FileProfile = components["schemas"]["FileProfile"];

export type ProfileState =
  | { kind: "loading" }
  | { kind: "pending" }
  | { kind: "ready"; profile: FileProfile }
  | { kind: "error"; message: string };

const POLL_INTERVAL_MS = 2000;

export interface UseProfileResult {
  state: ProfileState;
  refetch: () => Promise<void>;
}

export function useProfile(fileId: number): UseProfileResult {
  const [state, setState] = useState<ProfileState>({ kind: "loading" });
  const inFlight = useRef(false);

  const fetchOnce = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const { data, error, response } = await api.GET("/files/{file_id}/profile", {
        params: { path: { file_id: fileId } },
      });
      if (response.status === 404) {
        setState({ kind: "pending" });
      } else if (error) {
        setState({ kind: "error", message: stringifyError(error) });
      } else if (data) {
        setState({ kind: "ready", profile: data });
      }
    } finally {
      inFlight.current = false;
    }
  }, [fileId]);

  useEffect(() => {
    setState({ kind: "loading" });
    void fetchOnce();
  }, [fetchOnce]);

  useEffect(() => {
    if (state.kind !== "pending") return;
    const handle = window.setInterval(() => {
      void fetchOnce();
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(handle);
  }, [state, fetchOnce]);

  return { state, refetch: fetchOnce };
}
