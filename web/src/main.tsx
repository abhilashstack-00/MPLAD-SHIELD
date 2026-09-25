import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { ScoredProvider } from "./data/loadScored";
import "./styles/tokens.css";
import "./styles/app.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <ScoredProvider>
        <App />
      </ScoredProvider>
    </BrowserRouter>
  </StrictMode>
);
