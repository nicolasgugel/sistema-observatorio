import { createRoot } from "react-dom/client";
import App from "./App.tsx";
import "./index.css";

const rootElement = document.getElementById("root");
const fallbackElement = document.getElementById("boot-fallback");

function showFatalStartupError(message: string) {
  if (fallbackElement) {
    fallbackElement.innerHTML = `
      <div style="max-width: 720px;">
        <p style="margin: 0 0 8px; font-size: 18px; font-weight: 700; color: #991b1b;">No se pudo cargar la aplicacion</p>
        <p style="margin: 0 0 10px; font-size: 14px; color: #374151;">${message}</p>
        <p style="margin: 0; font-size: 13px; color: #6b7280;">
          Prueba recargar con Ctrl + F5. Si persiste, abre consola (F12) y comparte el error.
        </p>
      </div>
    `;
  }
}

window.addEventListener("error", (event) => {
  showFatalStartupError(event.message || "Error de JavaScript en el arranque.");
});

window.addEventListener("unhandledrejection", (event) => {
  const reasonText =
    typeof event.reason === "string"
      ? event.reason
      : event.reason && typeof event.reason.message === "string"
        ? event.reason.message
        : "Promesa rechazada no controlada durante el arranque.";
  showFatalStartupError(reasonText);
});

if (!rootElement) {
  showFatalStartupError("No se encontro el nodo #root.");
  throw new Error("Root element not found");
}

try {
  createRoot(rootElement).render(<App />);
  requestAnimationFrame(() => {
    fallbackElement?.remove();
  });
} catch (error) {
  const message = error instanceof Error ? error.message : "Error desconocido en el arranque.";
  showFatalStartupError(message);
  throw error;
}
