import { useState } from "react";
import { api } from "../api/client";
import { stringifyError } from "../lib/format";
import { useFiles } from "../lib/useFiles";
import { Dropzone, type UploadState } from "./Dropzone";
import { FileList } from "./FileList";
import { ProfileDrawer } from "./ProfileDrawer";

export function FileManager(): JSX.Element {
  const [openFileId, setOpenFileId] = useState<number | null>(null);
  const [uploadState, setUploadState] = useState<UploadState>({ kind: "idle" });
  const { files, isLoading, refetch } = useFiles();

  async function handleUpload(file: File): Promise<void> {
    setUploadState({ kind: "uploading", name: file.name });
    const body = new FormData();
    body.append("file", file);
    // openapi-fetch passes FormData through unchanged; the runtime
    // serializer skips JSON when the body is a multipart payload.
    const { error } = await api.POST("/files", { body: body as unknown as never });
    if (error) {
      setUploadState({ kind: "error", message: stringifyError(error) });
      return;
    }
    setUploadState({ kind: "idle" });
    await refetch();
  }

  return (
    <div className="fm">
      <header className="fm__header">
        <h1>StructAI</h1>
        <span className="fm__build">{import.meta.env.MODE}</span>
      </header>
      <main className="fm__main">
        <Dropzone onUpload={handleUpload} state={uploadState} />
        <FileList files={files} loading={isLoading} onOpen={setOpenFileId} />
      </main>
      {openFileId !== null && (
        <ProfileDrawer fileId={openFileId} onClose={() => setOpenFileId(null)} />
      )}
    </div>
  );
}
