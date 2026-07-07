import Link from "next/link";
import { SITE } from "@/lib/site";

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
          {/* Video removed for now (Taash's call) — showing the poster image only.
              To restore the player: swap this <img> back to <IntroVideo /> and
              re-import it. The component + /intro.mp4 are kept on disk. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img className="introvid" src={SITE.introPoster} alt="Taashira Chikosi — portfolio intro" />
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
