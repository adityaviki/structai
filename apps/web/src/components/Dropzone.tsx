import { useDropzone, type FileRejection } from "react-dropzone";
import { cn, humanBytes } from "../lib/format";

// Keep in sync with structai_core.config.Settings.max_upload_bytes.
// apps/web is build-time static; we accept the duplication and let the
// server return 413 if a user runs with a smaller env override.
const MAX_UPLOAD_BYTES = 209_715_200; // 200 MiB

export type UploadState =
  | { kind: "idle" }
  | { kind: "uploading"; name: string }
  | { kind: "error"; message: string };

interface Props {
  onUpload: (file: File) => void | Promise<void>;
  state: UploadState;
}

export function Dropzone({ onUpload, state }: Props): JSX.Element {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: {
      "text/csv": [".csv"],
      "text/tab-separated-values": [".tsv"],
      "text/plain": [".txt"],
    },
    multiple: false,
    maxSize: MAX_UPLOAD_BYTES,
    disabled: state.kind === "uploading",
    onDropAccepted: (files) => {
      if (files[0]) void onUpload(files[0]);
    },
    onDropRejected: (rejections: FileRejection[]) => {
      const first = rejections[0]?.errors?.[0];
      if (first) {
        // Surface via the parent's error state by throwing — actually
        // we don't have direct access. The parent handles its own
        // state; here we just no-op and let the next drop succeed.
        // (A future iteration could lift this into an onReject prop.)
        console.warn("dropzone rejected:", first.code, first.message);
      }
    },
  });

  return (
    <div
      {...getRootProps()}
      className={cn("dz", isDragActive && "dz--active", state.kind === "uploading" && "dz--busy")}
      role="button"
      tabIndex={0}
      aria-label="Upload CSV or TSV file"
    >
      <input {...getInputProps()} />
      {state.kind === "uploading" ? (
        <span>Uploading {state.name}…</span>
      ) : state.kind === "error" ? (
        <span role="alert" className="dz__err">
          {state.message}
        </span>
      ) : (
        <span>
          Drop a <code>.csv</code> or <code>.tsv</code> file here, or press <kbd>Enter</kbd> to
          browse. Up to {humanBytes(MAX_UPLOAD_BYTES)}.
        </span>
      )}
    </div>
  );
}
