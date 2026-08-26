import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@veyra/ui/styles/tokens.css";
import "@veyra/ui/styles/base.css";
import "@veyra/ui/styles/shell.css";
import "@veyra/ui/styles/primitives.css";
import "@veyra/connected-account/styles.css";
import "./app.css";
import { createLocalApiClient } from "./api/local-client";
import { DesktopApp } from "./app";

const root = document.getElementById("root");
if (!root) throw new Error("Desktop root element is missing");

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false },
    mutations: { retry: false },
  },
});
const localApi = createLocalApiClient();

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <DesktopApp api={localApi} />
    </QueryClientProvider>
  </StrictMode>,
);
