import { ImageResponse } from "next/og";
import { SITE } from "@/lib/site";

const TAGLINE = "Energy → Agentic AI → Agents";
export const alt = `${SITE.name} — ${TAGLINE}`;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

// Social-share card rendered at build time. Subset-of-CSS only; every container
// with >1 child must declare display:flex.
export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          backgroundColor: "#08090B",
          padding: "80px",
          position: "relative",
        }}
      >
        {/* blue glow */}
        <div
          style={{
            position: "absolute",
            top: -160,
            left: 420,
            width: 720,
            height: 460,
            borderRadius: "9999px",
            background: "#5B9CFF",
            opacity: 0.18,
            filter: "blur(120px)",
            display: "flex",
          }}
        />
        <div style={{ display: "flex", alignItems: "center", marginBottom: 30 }}>
          <div
            style={{
              width: 46,
              height: 46,
              borderRadius: 12,
              backgroundColor: "#5B9CFF",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              marginRight: 16,
              color: "#04173A",
              fontSize: 26,
              fontWeight: 700,
            }}
          >
            T
          </div>
          <div style={{ display: "flex", color: "#F2F3F5", fontSize: 28, fontWeight: 600 }}>
            {SITE.name}
          </div>
        </div>

        <div
          style={{
            display: "flex",
            color: "#F2F3F5",
            fontSize: 66,
            fontWeight: 600,
            lineHeight: 1.08,
            maxWidth: 960,
            letterSpacing: -1.5,
          }}
        >
          <span style={{ display: "flex", color: "#5B9CFF" }}>AI Systems&nbsp;</span>
          that Survive Contact With Reality
        </div>

        <div
          style={{
            display: "flex",
            color: "#9aa3b2",
            fontSize: 28,
            marginTop: 30,
            fontFamily: "monospace",
          }}
        >
          {TAGLINE}
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            marginTop: 44,
            color: "#626977",
            fontSize: 24,
          }}
        >
          <div
            style={{
              width: 10,
              height: 10,
              borderRadius: "9999px",
              backgroundColor: "#5BE38B",
              marginRight: 12,
              display: "flex",
            }}
          />
          Live, verified demos · real backends
        </div>
      </div>
    ),
    { ...size },
  );
}
