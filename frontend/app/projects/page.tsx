import { Suspense } from "react";
import type { Metadata } from "next";
import { ProjectsView } from "@/components/projects-view";

export const metadata: Metadata = {
  title: "Projects — Taashira Chikosi",
  description:
    "Live, verified projects across Agentic AI and Agents — each with a working demo against a real backend.",
};

export default function ProjectsPage() {
  return (
    <div id="view-projects">
      <Suspense fallback={null}>
        <ProjectsView />
      </Suspense>
    </div>
  );
}
