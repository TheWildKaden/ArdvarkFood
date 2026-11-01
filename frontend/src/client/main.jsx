import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import { SpotifyPlayerProvider } from "../../Apps/Spotify/SpotifyPlayerContext.jsx";
import "@fontsource/geist-sans/400.css";
import "@fontsource/geist-sans/500.css";
import "@fontsource/geist-sans/600.css";
import "@fontsource/geist-sans/700.css";
import "./styles/global.css";
import "./styles/revamp.css";
import "./styles/usability.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <SpotifyPlayerProvider>
        <App />
      </SpotifyPlayerProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
