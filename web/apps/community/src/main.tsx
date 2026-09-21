import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@veyra/ui/styles/tokens.css";
import "@veyra/ui/styles/base.css";
import "@veyra/ui/styles/shell.css";
import "@veyra/ui/styles/primitives.css";
import "@veyra/ui/styles/feedback.css";
import "@veyra/connected-account/styles.css";
import "./app.css";
import { CommunityApp } from "./app";

const root = document.getElementById("root");
if (!root) throw new Error("Community root element is missing");

createRoot(root).render(
  <StrictMode>
    <CommunityApp />
  </StrictMode>,
);
