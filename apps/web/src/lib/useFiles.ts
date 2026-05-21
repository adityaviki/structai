import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { components } from "../api/schema";
import { stringifyError } from "./format";

export type FileRow = components["schemas"]["FileSummary"];

const POLL_INTERVAL_MS = 2000;
const PENDING_STATUSES: ReadonlyArray<FileRow["status"]> = ["queued", "profiling"];

export interface UseFilesResult {
  files: FileRow[];
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useFiles(): UseFilesResult {
  const [files, setFiles] = useState<FileRow[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  const fetchOnce = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const { data, error: err } = await api.GET("/files");
      if (err) {
        setError(stringifyError(err));
      } else if (data) {
        setFiles(data.items);
        setError(null);
      }
    } finally {
      inFlight.current = false;
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchOnce();
  }, [fetchOnce]);

  useEffect(() => {
    const hasPending = files.some((f) => PENDING_STATUSES.includes(f.status));
    if (!hasPending) return;
    const handle = window.setInterval(() => {
      void fetchOnce();
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(handle);
  }, [files, fetchOnce]);

  return { files, isLoading, error, refetch: fetchOnce };
}
