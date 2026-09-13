// Directly opened files and local development use the local API. The deployed
// FastAPI app serves this frontend too, so it uses its own public origin.
const isLocal = window.location.protocol === "file:" ||
  ["localhost", "127.0.0.1"].includes(window.location.hostname);
const API_BASE_URL = isLocal ? "http://localhost:8000" : window.location.origin;
