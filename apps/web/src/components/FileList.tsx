import { humanBytes, relativeTime } from "../lib/format";
import type { FileRow } from "../lib/useFiles";
import { StatusBadge } from "./StatusBadge";

interface Props {
  files: FileRow[];
  loading: boolean;
  onOpen: (id: number) => void;
}

export function FileList({ files, loading, onOpen }: Props): JSX.Element {
  if (!loading && files.length === 0) {
    return (
      <div className="fl fl--empty">
        <p>No files yet. Drop one above to start.</p>
      </div>
    );
  }

  return (
    <table className="fl" aria-busy={loading}>
      <thead>
        <tr>
          <th scope="col">Name</th>
          <th scope="col">Size</th>
          <th scope="col">Uploaded</th>
          <th scope="col">Status</th>
        </tr>
      </thead>
      <tbody>
        {files.map((f) => (
          <tr
            key={f.id}
            tabIndex={0}
            role="button"
            aria-label={`Open profile for ${f.original_name}`}
            onClick={() => onOpen(f.id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onOpen(f.id);
              }
            }}
          >
            <td>{f.original_name}</td>
            <td>{humanBytes(f.bytes)}</td>
            <td>
              <time dateTime={f.uploaded_at}>{relativeTime(f.uploaded_at)}</time>
            </td>
            <td>
              <StatusBadge status={f.status} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
