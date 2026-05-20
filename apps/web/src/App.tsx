import { useEffect, useState } from "react";
import { api } from "./api/client";

export function App() {
  const [status, setStatus] = useState<string>("…");

  useEffect(() => {
    api.GET("/healthz").then(({ data, error }) => {
      if (error) {
        setStatus(`error: ${JSON.stringify(error)}`);
      } else if (data) {
        setStatus(data.status ?? "ok");
      }
    });
  }, []);

  return <div>api: {status}</div>;
}
