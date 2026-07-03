import type { Metadata } from "next";
import { SITE } from "@/lib/site";
import { CertImage } from "@/components/cert-image";

export const metadata: Metadata = {
  title: "Certifications — Taashira Chikosi",
  description: "Verified credentials and badges.",
};

export default function CertificationsPage() {
  return (
    <div id="view-certs">
      <header className="phead wrap" style={{ textAlign: "left", padding: "56px 32px 0" }}>
        <h1 data-reveal style={{ color: "var(--acc)" }}>
          Certifications
        </h1>
      </header>
      <div className="wrap" style={{ marginTop: 34 }}>
        <div className="certgrid">
          {SITE.certifications.map((c) => {
            const body = (
              <>
                <div className="cert-img">
                  <CertImage src={c.img} alt={`${c.name} certificate`} />
                </div>
                <div className="cert-body">
                  <b>{c.name}</b>
                  <span>
                    {c.issuer} · {c.year}
                  </span>
                  {c.url && (
                    <span
                      className="mono"
                      style={{
                        color: "var(--acc)",
                        fontSize: 11.5,
                        marginTop: 8,
                        letterSpacing: "0.04em",
                      }}
                    >
                      Verify on Coursera ↗
                    </span>
                  )}
                </div>
              </>
            );
            return c.url ? (
              <a
                key={c.name}
                className="cert"
                href={c.url}
                target="_blank"
                rel="noopener noreferrer"
                style={{ display: "block" }}
              >
                {body}
              </a>
            ) : (
              <div key={c.name} className="cert">
                {body}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
