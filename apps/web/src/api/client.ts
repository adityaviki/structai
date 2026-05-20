import createClient from "openapi-fetch";
import type { paths } from "./schema";

// In dev, Vite proxies /api/* to FastAPI on :8000 (see vite.config.ts).
// In prod, the API is served from the same origin behind /api.
export const api = createClient<paths>({ baseUrl: "/api" });
