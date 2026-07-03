"use client";

import { useRef, useState } from "react";
import { SITE } from "@/lib/site";

// Intro video (home hero). Before first play it shows the poster with a big blue
// play affordance — a constantly-pulsing ring (ambient motion to invite the click)
// that brightens on hover. On play it hands off to native controls.
export function IntroVideo() {
  const ref = useRef<HTMLVideoElement>(null);
  const [started, setStarted] = useState(false);

  const start = () => {
    setStarted(true);
    ref.current?.play().catch(() => {});
  };

  // When the video finishes, return to the thumbnail: reload restores the poster
  // frame (not the last frame), and hiding controls brings back the play button.
  const reset = () => {
    setStarted(false);
    ref.current?.load();
  };

  return (
    <div className="introvid-wrap">
      <video
        ref={ref}
        className="introvid"
        controls={started}
        playsInline
        preload="metadata"
        poster={SITE.introPoster}
        aria-label="Intro video — who I am, what I build, why it matters"
        onPlay={() => setStarted(true)}
        onEnded={reset}
      >
        <source src={SITE.introVideo} type="video/mp4" />
      </video>
      {!started && (
        <button type="button" className="introvid-play" onClick={start} aria-label="Play intro video">
          <span className="introvid-ring" aria-hidden="true" />
          <span className="introvid-ring introvid-ring-2" aria-hidden="true" />
          <span className="introvid-btn" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M8 5v14l11-7z" />
            </svg>
          </span>
        </button>
      )}
    </div>
  );
}
