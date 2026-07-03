// Single source of truth for site-wide constants + home copy.
// Home copy is ported verbatim from mockups/portfolio-v3 (the design source).

export const SITE = {
  name: "Taashira Chikosi",
  // Hero (mockup): eyebrow + headline with "AI Systems" highlighted.
  eyebrow: "Energy Modelling → Agentic AI",
  headlineLead: "How much can we actually trust AI?",
  headlineHl: "I'm building to find out.",
  videoTag: "● Intro · 60s",
  videoMeta: "Who I am · what I build · why it matters — in my own words.",
  // About Me — verbatim from the mockup.
  about: [
    "An energy efficiency engineer who spent years modelling how buildings consume power. As data and AI reshaped every industry, I saw systems that can reason, decide, and act autonomously across entire workflows were the direction industries are heading in.",
    "Now I aim to build Agentic AI with an engineer's discipline — Defining problems, Designing Solutions, Testing and Evaluating, Analyzing Results, Iterating and Improving.",
    "I'm based in Sydney, building toward AI engineer roles — and always up for a conversation about building things that hold up under pressure.",
  ],
  // Contact (mockup uses the outlook address on the public site).
  email: "taashira.wesley@outlook.com",
  github: "https://github.com/taashchikosi",
  linkedin: "https://www.linkedin.com/in/taashira-chikosi/",
  domain: "taash-portfolio.vercel.app",
  // Résumé PDF lives in frontend/public/ → served at this root path.
  resume: "/Taash_Chikosi_Resume.pdf",
  resumeReady: true,
  // Verified Coursera credentials — surfaced under Résumé ▾ → Certifications.
  certifications: [
    {
      name: "AI Product Management",
      issuer: "Duke University",
      year: "2025",
      url: "https://www.coursera.org/account/accomplishments/specialization/JTZTS5SW09YS",
      // Drop a certificate screenshot here → it replaces the medal icon automatically.
      img: "/certs/ai-product-management.png",
    },
    {
      name: "Google Data Analytics",
      issuer: "Google",
      year: "2022",
      url: "https://www.coursera.org/account/accomplishments/specialization/certificate/6KZW45K5L3L9",
      img: "/certs/google-data-analytics.png",
    },
    {
      name: "Case-Based Frameworks for Mastering Management Consulting",
      issuer: "Board Infinity",
      year: "2023",
      url: "https://www.coursera.org/account/accomplishments/verify/J09ZALMIIWUJ",
      img: "/certs/management-consulting.png",
    },
  ],
  // Intro video — v3 final (35.5s, 1080p web embed). Build plan: Intro_Video_v3_Build_Plan.md.
  introVideoReady: true,
  introVideo: "/intro.mp4",
  introPoster: "/intro-poster.jpg",
};
