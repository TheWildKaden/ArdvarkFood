import { useEffect, useRef, useState } from "react";
import { ArrowRight, AudioLines, ChartNoAxesCombined, Volume2, VolumeX } from "lucide-react";
import "./WelcomeScreen.css";

const musicSource = "/audio/stock-watch-ambience.wav";

export default function WelcomeScreen({ onEnter }) {
  const sceneRef = useRef(null);
  const audioRef = useRef(null);
  const [musicEnabled, setMusicEnabled] = useState(false);
  const [musicUnavailable, setMusicUnavailable] = useState(false);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return undefined;
    audio.volume = 0.22;
    const tryAutoplay = async () => {
      try {
        await audio.play();
        setMusicEnabled(true);
      } catch {
        setMusicEnabled(false);
      }
    };
    void tryAutoplay();
    return () => audio.pause();
  }, []);

  function moveParallax(event) {
    if (!sceneRef.current || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const bounds = sceneRef.current.getBoundingClientRect();
    const x = ((event.clientX - bounds.left) / bounds.width - 0.5) * 2;
    const y = ((event.clientY - bounds.top) / bounds.height - 0.5) * 2;
    sceneRef.current.style.setProperty("--parallax-x", `${x.toFixed(3)}`);
    sceneRef.current.style.setProperty("--parallax-y", `${y.toFixed(3)}`);
  }

  async function toggleMusic() {
    const audio = audioRef.current;
    if (!audio) return;
    if (musicEnabled) {
      audio.pause();
      setMusicEnabled(false);
      return;
    }
    try {
      await audio.play();
      setMusicEnabled(true);
      setMusicUnavailable(false);
    } catch (error) {
      console.error("Unable to play the welcome music", error);
      setMusicUnavailable(true);
    }
  }

  function enterWorkspace() {
    if (leaving) return;
    setLeaving(true);
    window.setTimeout(onEnter, 680);
  }

  return (
    <section
      className={`welcome-screen${leaving ? " welcome-screen-leaving" : ""}`}
      ref={sceneRef}
      onPointerMove={moveParallax}
      aria-label="Kaden's Stock Watch welcome screen"
    >
      <audio ref={audioRef} src={musicSource} loop preload="auto" />
      <div className="welcome-grain" />
      <div className="welcome-orbit welcome-orbit-back" />
      <div className="welcome-orbit welcome-orbit-front" />
      <div className="welcome-chart" aria-hidden="true">
        <div className="welcome-chart-grid" />
        <svg viewBox="0 0 1440 560" preserveAspectRatio="none">
          <defs>
            <linearGradient id="welcome-line" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#90aaff" stopOpacity="0" />
              <stop offset="42%" stopColor="#90aaff" stopOpacity=".33" />
              <stop offset="100%" stopColor="#90aaff" stopOpacity=".86" />
            </linearGradient>
            <linearGradient id="welcome-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#7996f2" stopOpacity=".17" />
              <stop offset="100%" stopColor="#7996f2" stopOpacity="0" />
            </linearGradient>
          </defs>
          <path className="welcome-chart-fill" d="M0 423 104 398 180 413 276 347 354 367 438 311 515 335 611 270 700 301 786 224 866 252 960 196 1044 220 1125 145 1192 181 1275 112 1343 137 1440 56V560H0Z" />
          <path className="welcome-chart-line" d="M0 423 104 398 180 413 276 347 354 367 438 311 515 335 611 270 700 301 786 224 866 252 960 196 1044 220 1125 145 1192 181 1275 112 1343 137 1440 56" />
          <circle className="welcome-chart-point" cx="1275" cy="112" r="4" />
        </svg>
      </div>

      <header className="welcome-topline">
        <span className="welcome-brand-mark" aria-hidden="true"><span /></span>
        <span className="welcome-brand-name">KADEN'S <span>STOCK WATCH</span></span>
        <span className="welcome-owner">AN INDEPENDENT MARKET WORKSPACE</span>
      </header>

      <main className="welcome-content">
        <div className="welcome-kicker"><span /> A CLEARER VIEW OF THE MARKET</div>
        <h1>Markets,<br /><span>in focus.</span></h1>
        <p className="welcome-description">A considered workspace for the markets you follow.</p>
        <div className="welcome-action-row">
          <button
            className={`welcome-audio welcome-audio-button${musicEnabled ? " is-playing" : ""}`}
            onClick={toggleMusic}
            type="button"
            aria-label={musicEnabled ? "Mute welcome music" : "Play welcome music"}
            title={musicUnavailable ? "Unable to play welcome music" : musicEnabled ? "Mute welcome music" : "Play welcome music"}
          >
            {musicEnabled ? <AudioLines size={17} /> : musicUnavailable ? <VolumeX size={17} /> : <Volume2 size={17} />}
          </button>
          <div className="welcome-loader-card" role="status" aria-live="polite">
            <span className={`welcome-loader-icon${leaving ? " is-opening" : ""}`}><ChartNoAxesCombined size={15} /></span>
            <span className="welcome-loader-copy">
              <strong>{leaving ? "OPENING WORKSPACE" : "LOCAL WORKSPACE"}</strong>
              <small>{musicUnavailable ? "Audio could not be played" : musicEnabled ? "Original ambient soundtrack playing" : "Your markets. Your perspective."}</small>
            </span>
            <span className={`welcome-equalizer${musicEnabled ? " is-active" : ""}`} aria-hidden="true"><i /><i /><i /><i /></span>
          </div>
          <button
            type="button"
            className="welcome-enter"
            onClick={enterWorkspace}
            disabled={leaving}
            aria-label="Enter Kaden's Stock Watch"
            title="Enter workspace"
          >
            <ArrowRight size={19} />
          </button>
        </div>
        <div className="welcome-footnote">{leaving ? "GETTING THINGS IN FOCUS…" : "CLICK THE ARROW TO BEGIN"}</div>
      </main>

      <aside className="welcome-side-note" aria-hidden="true"><span>01</span><i /> MARKET OVERVIEW</aside>

      <footer className="welcome-footer">
        <span>DESIGNED FOR THE LONG VIEW</span>
        <span>ORIGINAL AMBIENT AUDIO</span>
        <span>© {new Date().getFullYear()} KADEN</span>
      </footer>
    </section>
  );
}
