"use client";

import { useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { PROJECTS, LANE_META, LANE_ORDER, type LaneKey } from "@/lib/projects";

const COUNTS: Record<LaneKey, number> = {
  agentic: PROJECTS.filter((p) => p.lane === "agentic").length,
  automation: PROJECTS.filter((p) => p.lane === "automation").length,
};

export function ProjectsView() {
  const params = useSearchParams();
  const initial = (params.get("lane") as LaneKey) || "agentic";
  const [cat, setCat] = useState<LaneKey>(
    LANE_ORDER.includes(initial) ? initial : "agentic"
  );
  const accent = LANE_META[cat].accent;
  const shown = PROJECTS.filter((p) => p.lane === cat);

  return (
    <>
      <header className="phead wrap">
        <h1 data-reveal style={{ color: "var(--acc)" }}>
          Projects
        </h1>
        <div className="tabs" data-reveal role="tablist" aria-label="Filter projects by lane">
          {LANE_ORDER.map((key) => {
            const on = key === cat;
            return (
              <button
                key={key}
                role="tab"
                aria-selected={on}
                className={`tab${on ? " on" : ""}`}
                style={on ? { borderColor: LANE_META[key].accent } : undefined}
                onClick={() => setCat(key)}
              >
                <span className="dot" style={{ background: LANE_META[key].accent }} />
                {LANE_META[key].name} <span className="cnt">{COUNTS[key]}</span>
              </button>
            );
          })}
        </div>
      </header>

      <div className="wrap">
        <div className="grid">
          {shown.map((p, i) => (
            <Link
              key={p.slug}
              href={p.href}
              className="card"
              style={{ ["--ca" as string]: accent }}
              aria-label={`${p.name} — Live`}
            >
              <div className="card-imgwrap">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={p.img} alt={`${p.name} — illustrative hero image`} loading="lazy" />
              </div>
              <div className="card-body">
                <div className="row">
                  <span className="ix">0{i + 1}</span>
                  <span className="lane">{LANE_META[cat].name}</span>
                </div>
                <h3>{p.name}</h3>
                <p>{p.one}</p>
                <div className="cfoot">
                  <span className="status">
                    <span className="d live" style={{ background: "var(--green)" }} />
                    Live
                  </span>
                  <span className="golive">
                    Live demo
                    <svg
                      className="icn arr"
                      viewBox="0 0 24 24"
                      style={{ stroke: accent, width: 15, height: 15 }}
                    >
                      <path d="M5 12h14M13 6l6 6-6 6" />
                    </svg>
                  </span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </>
  );
}
