// Case-study page renderer — reproduces mockups/portfolio-v3 openCase() exactly.
// Server component; the live demo is passed in as the `demo` slot (a client
// component) and rendered inside the "Live Demo" panel where the mockup had its
// placeholder. One CasePage drives all 8 case routes → identical structure.

import Link from "next/link";
import { type Project, LANE_META } from "@/lib/projects";

const GH_PATH =
  "M9 19c-5 1.5-5-2.5-7-3m14 6v-3.5a3 3 0 00-.8-2.3c2.7-.3 5.5-1.3 5.5-6a4.6 4.6 0 00-1.3-3.2 4.3 4.3 0 00-.1-3.2s-1-.3-3.5 1.3a12 12 0 00-6.3 0C6 1.6 5 1.9 5 1.9a4.3 4.3 0 00-.1 3.2A4.6 4.6 0 003.5 8.3c0 4.6 2.8 5.7 5.5 6a3 3 0 00-.8 2.2V21";

function Panel({
  kk,
  id,
  children,
}: {
  kk?: string;
  id?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="panel" id={id} data-reveal style={id ? { scrollMarginTop: 80 } : undefined}>
      {kk && <div className="kk">{kk}</div>}
      {children}
    </div>
  );
}

function Figure({ d }: { d: { file: string; label: string; cap: string } }) {
  return (
    <div className="figure">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={d.file} alt={`${d.label} diagram`} />
      <div className="figcap">{d.cap}</div>
    </div>
  );
}

function Overview({ project, accent }: { project: Project; accent: string }) {
  const { ov, applies } = project;
  return (
    <div className="ov" style={{ ["--oc" as string]: accent }}>
      <div className="ov-block">
        <div className="ov-label">The problem</div>
        <p>{ov.problem}</p>
      </div>
      <div className="ov-block">
        <div className="ov-label">What this project is</div>
        <p>{ov.what}</p>
      </div>
      <div className="ov-block">
        <div className="ov-label">How it solves the problem</div>
        <ul className="ov-list">
          {ov.how.map((x) => (
            <li key={x}>{x}</li>
          ))}
        </ul>
      </div>
      {ov.note && (
        <div className="ov-block">
          <div className="ov-label">Business impact</div>
          {ov.note.split("\n\n").map((para, i) => (
            <p key={i}>{para}</p>
          ))}
        </div>
      )}
      {applies && (
        <div className="applies">
          <span className="lbl">Also fits</span>
          {applies.map((a) => (
            <span className="chip" key={a}>
              {a}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function Pills({ pillars }: { pillars: NonNullable<Project["pillars"]> }) {
  return (
    <div className="pills">
      {pillars.map((p) => (
        <div className={`pill${p.caveat ? " caveat" : ""}`} key={p.t}>
          <div className="pt">
            <span
              className="sq"
              // dot matches the page's lane glow (--btn-acc); caveat pillars stay amber (a warning)
              style={{ background: p.caveat ? "var(--amber)" : "var(--btn-acc, var(--acc))" }}
            />
            {p.t}
          </div>
          <p>{p.m}</p>
        </div>
      ))}
    </div>
  );
}

export function CasePage({
  project,
  demo,
}: {
  project: Project;
  demo: React.ReactNode;
}) {
  const accent = LANE_META[project.lane].accent;
  const laneName = LANE_META[project.lane].name;
  const isLive = project.status === "live";
  const ghLabel = project.repo === PROFILE ? "GitHub" : "GitHub repo";

  // The Live Demo panel: CTA framing comes from the slotted client demo widget;
  // the panel adds the heading + the honest note (+ offline badge for traces).
  const demoPanel = (
    <Panel kk="Live Demo" id="demo">
      {project.demo.blurb && <p className="demo-blurb">{project.demo.blurb}</p>}
      {project.demo.kind === "trace" && (
        <div className="cs-cta" style={{ margin: "0 0 16px" }}>
          <span className="offline">offline-validated</span>
        </div>
      )}
      {demo}
      {project.demo.note && <div className="note">{project.demo.note}</div>}
    </Panel>
  );

  return (
    <div className="wrap case-page" data-slug={project.slug} data-lane={project.lane} style={{ ["--btn-acc" as string]: accent }}>
      <Link href="/projects" className="back">
        <svg className="icn" viewBox="0 0 24 24">
          <path d="M19 12H5M11 6l-6 6 6 6" />
        </svg>
        All projects
      </Link>

      <div className="cs-banner" data-reveal>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={project.img} alt={`${project.name} — hero image`} />
      </div>

      <div className="cs-hero">
        <span className="eyebrow" data-reveal style={{ color: accent }}>
          {laneName} · case study
        </span>
        <h1 data-reveal>{project.name}</h1>
        <div className="cs-cta" data-reveal>
          <span className="status">
            <span
              className={`d${isLive ? " live" : ""}`}
              style={{ background: isLive ? "var(--green)" : "var(--amber)" }}
            />
            {isLive ? "Live" : "In progress"}
          </span>
          <a
            className="btn gh"
            href={project.repo}
            target="_blank"
            rel="noopener noreferrer"
          >
            <svg className="icn" viewBox="0 0 24 24">
              <path d={GH_PATH} />
            </svg>
            {ghLabel}
          </a>
        </div>
      </div>

      <div className="cs-body">
        <Panel kk="Overview">
          <Overview project={project} accent={accent} />
        </Panel>

        {project.lane === "agentic" && (
          <>
            <Panel kk="System Architecture">
              <Figure d={project.diagrams[0]} />
            </Panel>
            {project.toolctx && (
              <Panel kk="Tool design & context management">
                <p
                  className="toolctx"
                  dangerouslySetInnerHTML={{ __html: project.toolctx }}
                />
              </Panel>
            )}
            {project.diagrams[1] && (
              <Panel kk="Agent Architecture">
                <Figure d={project.diagrams[1]} />
              </Panel>
            )}
            <Panel kk="Tech Stack">
              <StackRow stack={project.stack} accent={accent} />
            </Panel>
            {demoPanel}
            {project.result && (
              <Panel kk="Results">
                <p className="result-lead">{project.result}</p>
              </Panel>
            )}
            {project.pillars && (
              <Panel kk="Discussion">
                <Pills pillars={project.pillars} />
              </Panel>
            )}
          </>
        )}

        {project.lane === "automation" && (
          <>
            <Panel kk="System Architecture">
              <Figure d={project.diagrams[0]} />
            </Panel>
            <Panel kk="Tech Stack">
              <StackRow stack={project.stack} accent={accent} />
            </Panel>
            {demoPanel}
            {project.result && (
              <Panel kk="Results">
                <p className="result-lead">{project.result}</p>
              </Panel>
            )}
            {project.pillars && (
              <Panel kk="Discussion">
                <Pills pillars={project.pillars} />
              </Panel>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// Every tech-stack chip on a project page uses that project's single lane colour
// (blue = agentic · aqua = agents · gold = ml), passed in as `accent`. The old
// per-category hue scheme was dropped so the row reads as one consistent lane accent.
function StackRow({ stack, accent }: { stack: string[]; accent: string }) {
  return (
    <div className="stack-row">
      {stack.map((x) => (
        <span
          className="tg"
          key={x}
          style={{
            color: accent,
            background: `color-mix(in srgb, ${accent} 15%, transparent)`,
            borderColor: `color-mix(in srgb, ${accent} 42%, transparent)`,
          }}
        >
          {x}
        </span>
      ))}
    </div>
  );
}

const PROFILE = "https://github.com/taashchikosi";
