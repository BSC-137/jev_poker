import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { Votes } from "./votes";
import "./styles.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("root element is missing");
}
const votes = window.location.pathname === "/votes" || window.location.pathname === "/votes/";
createRoot(root).render(<StrictMode>{votes ? <Votes /> : <App />}</StrictMode>);
