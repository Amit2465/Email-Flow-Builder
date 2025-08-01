import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import App from "./App"
import "./index.css"

// Wait for DOM to be ready
document.addEventListener("DOMContentLoaded", () => {
  const container = document.getElementById("root")

  if (!container) {
    console.error("Root element with id 'root' not found in the DOM")
    return
  }

  const root = createRoot(container)
  root.render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
})

// Fallback if DOMContentLoaded already fired
if (document.readyState === "loading") {
  // DOM is still loading, event listener will handle it
} else {
  // DOM is already loaded
  const container = document.getElementById("root")

  if (!container) {
    console.error("Root element with id 'root' not found in the DOM")
  } else {
    const root = createRoot(container)
    root.render(
      <StrictMode>
        <App />
      </StrictMode>,
    )
  }
}
