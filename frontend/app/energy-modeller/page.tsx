import type { Metadata } from "next";
import { PROJECTS, LANE_META } from "@/lib/projects";
import { CasePage } from "@/components/case-ui";
import { Demo } from "./demo";
const P = PROJECTS.find((p) => p.slug === "energy-modeller")!;
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "https://204-168-226-100.sslip.io";
export const metadata: Metadata = { title: `${P.name} — Taashira Chikosi`, description: P.one };
export default function Page() {
  return <CasePage project={P} demo={<Demo apiBase={API_BASE} accent={LANE_META[P.lane].accent} />} />;
}
