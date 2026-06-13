// Project registry — the home page grid renders from this list.
// Adding a project = add an entry here + a page under app/<slug>/.

export type ProjectStatus = "live" | "in-progress" | "planned";

export type Project = {
  slug: string;
  title: string;
  tagline: string;
  blurb: string;
  tags: string[];
  status: ProjectStatus;
  href?: string; // internal case-study route; omit for planned projects
  repo?: string;
};

export const PROJECTS: Project[] = [
  {
    slug: "retrofitgpt",
    title: "RetrofitGPT",
    tagline: "Autonomous building decarbonisation advisor",
    blurb:
      "A five-agent system that turns a building energy model + 12 months of bills into an audit-ready retrofit business case — running real EnergyPlus behind an MCP physics layer, verified against ASHRAE Guideline 14, an OWASP-LLM06 guardrail, and real NCC 2022 Section J code compliance.",
    tags: ["LangGraph", "MCP", "EnergyPlus", "Claude + DeepSeek", "Next.js"],
    status: "live",
    href: "/retrofitgpt",
    repo: "https://github.com/taashchikosi/Taash_Chikosi_Portfolio",
  },
  {
    slug: "auditagent",
    title: "AuditAgent",
    tagline: "Citation-anchored contract-review agent",
    blurb:
      "A four-agent LangGraph pipeline that flags high-risk contract clauses and cites the exact source span for every finding — or rejects it. Measured against CUAD (real lawyer labels): the verified citation anchorer lifts faithfulness +0.29 on a reproducible 102-contract benchmark. Built for Big-4 contract review.",
    tags: ["LangGraph", "Citation gate", "CUAD eval", "DeepSeek + Claude", "Next.js"],
    // Flip to "live" once the backend is deployed and NEXT_PUBLIC_AUDITAGENT_API_BASE is set.
    status: "in-progress",
    href: "/auditagent",
    repo: "https://github.com/taashchikosi/auditagent",
  },
];
