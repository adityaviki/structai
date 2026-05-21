/**
 * Frontend smoke tests for the Phase 1 FileManager UI.
 *
 * Mocks the typed `api` client (openapi-fetch wrapper) so each test
 * controls the response of `GET /files` / `POST /files` /
 * `GET /files/:id/profile`. We assert on:
 *
 *   1. Drop a file → POST succeeds → row appears in the list and a
 *      poll cycle begins.
 *   2. Open a profile drawer → the literal `<EMAIL_1>` placeholder is
 *      rendered as text (not parsed as HTML, not turned into a link).
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FileManager } from "../components/FileManager";

const getMock = vi.fn();
const postMock = vi.fn();

vi.mock("../api/client", () => ({
  api: {
    GET: (...args: unknown[]) => getMock(...args),
    POST: (...args: unknown[]) => postMock(...args),
  },
}));

const SAMPLE_FILE = {
  id: 1,
  original_name: "simple.csv",
  bytes: 24,
  source_sha256: "a".repeat(64),
  uploaded_at: new Date().toISOString(),
  status: "queued" as const,
  profile_id: null,
};

beforeEach(() => {
  getMock.mockReset();
  postMock.mockReset();
});


describe("FileManager", () => {
  it("renders an uploaded file in the list after a successful POST", async () => {
    getMock.mockResolvedValueOnce({ data: { items: [] }, error: undefined, response: { status: 200 } });
    postMock.mockResolvedValueOnce({ data: SAMPLE_FILE, error: undefined, response: { status: 201 } });
    getMock.mockResolvedValueOnce({
      data: { items: [SAMPLE_FILE] },
      error: undefined,
      response: { status: 200 },
    });

    render(<FileManager />);

    // Empty state before any uploads.
    expect(await screen.findByText(/No files yet/)).toBeInTheDocument();

    // Find the hidden file input rendered by react-dropzone and drive it
    // directly. react-dropzone's drag-drop event simulation is finicky in
    // jsdom; the input path is the same code path for the keyboard /
    // file-picker case.
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    expect(input).toBeTruthy();

    const file = new File(["id,name\n1,alice\n"], "simple.csv", { type: "text/csv" });
    await act(async () => {
      Object.defineProperty(input, "files", { value: [file], configurable: true });
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });

    await waitFor(() => {
      expect(postMock).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.getByText("simple.csv")).toBeInTheDocument();
    });
    expect(screen.getByText(/Queued/)).toBeInTheDocument();
  });

  it("renders <EMAIL_N> placeholders as literal text in the profile drawer", async () => {
    const profiled = { ...SAMPLE_FILE, status: "profiled" as const, profile_id: 7 };
    getMock.mockResolvedValueOnce({
      data: { items: [profiled] },
      error: undefined,
      response: { status: 200 },
    });
    getMock.mockResolvedValueOnce({
      data: {
        row_count: 5,
        duplicate_row_count: 0,
        encoding: "utf-8",
        delimiter: ",",
        has_header: true,
        source_sha256: profiled.source_sha256,
        profile_sha256: "b".repeat(64),
        profile_version: "v1",
        raw_to_safe: { email: "email" },
        columns: [
          {
            name: "email",
            safe_name: "email",
            position: 0,
            inferred_type: "string",
            null_count: 0,
            null_rate: 0.0,
            empty_string_count: 0,
            distinct_count: 5,
            cardinality_class: "low",
            sample_values: ["<EMAIL_1>", "<EMAIL_2>", "<EMAIL_3>"],
            top_k: [{ value: "<EMAIL_1>", count: 1 }],
            pattern_hits: { email: 1.0 },
            pii_class: "email",
            pii_warnings: [],
            pk_score: 0.5,
            outlier_examples: [],
          },
        ],
        omitted_columns: [],
      },
      error: undefined,
      response: { status: 200 },
    });

    render(<FileManager />);

    const row = await screen.findByText("simple.csv");
    await act(async () => {
      row.closest("tr")?.click();
    });

    // Placeholder text appears literally — it's wrapped in <code> in the UI.
    await waitFor(() => {
      expect(screen.getAllByText("<EMAIL_1>").length).toBeGreaterThanOrEqual(1);
    });
    // The PII badge for the column should also show up.
    expect(screen.getByText(/PII: email/)).toBeInTheDocument();
  });
});
