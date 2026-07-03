import Link from "next/link";
import { SITE } from "@/lib/site";
import { IntroVideo } from "@/components/intro-video";

// Home view — ported from mockups/portfolio-v3: hero + intro video (sanctioned
// placeholder) + About Me + Lets Talk. No project grid (that lives at /projects).
export default function HomePage() {
  return (
    <div id="view-home">
      <header className="hero wrap">
        <span className="eyebrow" data-reveal>
          {SITE.eyebrow}
        </span>
        <h1 data-reveal>
          {SITE.headlineLead}
          <br />
          <span className="hl">{SITE.headlineHl}</span>
        </h1>
        <div className="cta" data-reveal>
          <Link className="btn pri" href="/projects">
            View live demos
            <svg className="icn" viewBox="0 0 24 24" style={{ stroke: "var(--acc-ink)" }}>
              <path d="M5 12h14M13 6l6 6-6 6" />
            </svg>
          </Link>
        </div>

        <div className="stage" data-reveal>
          {SITE.introVideoReady ? (
            /* Intro video — v3 final (see Intro_Video_v3_Build_Plan.md). */
            <IntroVideo />
          ) : (
            /* Placeholder — sanctioned until the real video ships. */
            <div
              className="video"
              role="img"
              aria-label="Intro video — coming soon"
              title="Intro video — coming soon"
            >
              <span className="vtag">{SITE.videoTag}</span>
              <div className="play" aria-hidden="true">
                <svg viewBox="0 0 24 24">
                  <path d="M8 5v14l11-7z" />
                </svg>
              </div>
              <span className="vmeta">{SITE.videoMeta}</span>
            </div>
          )}
        </div>
      </header>

      <section className="wrap about">
        <div className="home-block">
          <div className="about-single" data-reveal>
            <h2>About Me</h2>
            {SITE.about.map((p, i) => (
              <p key={i}>{p}</p>
            ))}
          </div>
        </div>
      </section>

      <section className="wrap" style={{ paddingTop: 44 }}>
        <div className="home-block">
          <h2 style={{ marginBottom: "22px" }} data-reveal>
            Let&apos;s Talk
          </h2>
          <div className="contact" data-reveal>
            <a className="ct" href={`mailto:${SITE.email}`}>
            <svg className="icn" viewBox="0 0 24 24">
              <path d="M3 7l9 6 9-6M3 7v10a1 1 0 001 1h16a1 1 0 001-1V7" />
            </svg>
            {SITE.email}
          </a>
          <a className="ct" href={SITE.linkedin} target="_blank" rel="noopener noreferrer">
            <svg className="icn" viewBox="0 0 24 24">
              <path d="M16 8a6 6 0 016 6v6h-4v-6a2 2 0 00-4 0v6h-4v-10h4v2" />
              <circle cx="4" cy="4" r="2" />
              <path d="M2 9h4v11H2z" />
            </svg>
            LinkedIn
          </a>
          </div>
        </div>
      </section>
    </div>
  );
}
