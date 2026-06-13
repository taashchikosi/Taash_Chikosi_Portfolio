import { ImageResponse } from "next/og";
import { SITE } from "@/lib/site";

export const alt = `${SITE.name} — ${SITE.role}`;
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
          backgroundColor: "#0a0a0b",
          padding: "80px",
          position: "relative",
        }}
      >
        {/* green glow */}
        <div
          style={{
            position: "absolute",
            top: -160,
            left: 380,
            width: 700,
            height: 460,
            borderRadius: "9999px",
            background: "#10b981",
            opacity: 0.18,
            filter: "blur(120px)",
            display: "flex",
          }}
        />
        <div style={{ display: "flex", alignItems: "center", marginBottom: 28 }}>
          <div
            style={{
              width: 44,
              height: 44,
              borderRadius: 10,
              backgroundColor: "#10b98122",
              border: "1px solid #10b98155",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              marginRight: 16,
            }}
          >
            <div style={{ display: "flex", fontSize: 26 }}>⚡</div>
          </div>
          <div style={{ display: "flex", color: "#10b981", fontSize: 26, fontWeight: 600 }}>
            {SITE.name}
          </div>
        </div>

        <div
          style={{
            display: "flex",
            color: "#ffffff",
            fontSize: 64,
            fontWeight: 700,
            lineHeight: 1.1,
            maxWidth: 920,
            letterSpacing: -1,
          }}
        >
          Autonomous AI systems for the built environment — shipped live.
        </div>

        <div
          style={{
            display: "flex",
            color: "#a1a1aa",
            fontSize: 30,
            marginTop: 30,
          }}
        >
          {SITE.role}
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            marginTop: 44,
            color: "#71717a",
            fontSize: 24,
          }}
        >
          <div
            style={{
              width: 10,
              height: 10,
              borderRadius: "9999px",
              backgroundColor: "#10b981",
              marginRight: 12,
              display: "flex",
            }}
          />
          RetrofitGPT · live multi-agent demo
        </div>
      </div>
    ),
    { ...size },
  );
}
