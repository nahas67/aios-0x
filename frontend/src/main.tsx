import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

// UI v2 — dense terminal rebuild. Set V2_UI=0 to fall back to the v1 app.
const v2 = import.meta.env.VITE_V2_UI !== "0";

const root = createRoot(document.getElementById("root")!);

if (v2) {
  void import("./v2").then(({ V2App }) => {
    root.render(
      <StrictMode>
        <V2App />
      </StrictMode>,
    );
  });
} else {
  void (async () => {
    await import("./styles/tokens.css");
    await import("./styles/shell.css");
    await import("./styles/components.css");
    const { App } = await import("./app/App");
    root.render(
      <StrictMode>
        <App />
      </StrictMode>,
    );
  })();
}
