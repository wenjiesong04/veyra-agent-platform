import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { brandIconUrl } from "@veyra/ui";
import "@veyra/ui/styles/tokens.css";
import "@veyra/ui/styles/base.css";
import "@veyra/ui/styles/shell.css";
import "@veyra/ui/styles/primitives.css";
import "@veyra/ui/styles/feedback.css";
import "@veyra/connected-account/styles.css";
import "./app.css";
import { CommunitySite } from "./site";

const root = document.getElementById("root");
if (!root) throw new Error("Community root element is missing");

const favicon = document.createElement("link");
favicon.rel = "icon";
favicon.type = "image/png";
favicon.href = brandIconUrl;
document.head.append(favicon);

createRoot(root).render(
  <StrictMode>
    <CommunitySite />
  </StrictMode>,
);
