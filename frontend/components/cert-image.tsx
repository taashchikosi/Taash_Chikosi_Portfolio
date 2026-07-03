"use client";

import { useEffect, useRef, useState } from "react";

// Shows the medal icon until the certificate screenshot has actually loaded, then
// reveals the photo. Handles the cached/already-complete case (where onLoad would
// fire before React attaches the handler) by checking img.complete on mount. A
// missing /certs/<file>.png stays as the medal — drop the file in and it appears.
export function CertImage({ src, alt }: { src?: string; alt: string }) {
  const [loaded, setLoaded] = useState(false);
  const ref = useRef<HTMLImageElement>(null);

  useEffect(() => {
    const img = ref.current;
    if (img && img.complete && img.naturalWidth > 0) setLoaded(true);
  }, [src]);

  return (
    <>
      {!loaded && (
        <svg
          viewBox="0 0 24 24"
          width="42"
          height="42"
          style={{ stroke: "var(--acc)", fill: "none", strokeWidth: 1.6 }}
          aria-hidden
        >
          <circle cx="12" cy="9" r="5" />
          <path d="M8.5 13.2L7 22l5-3 5 3-1.5-8.8" />
        </svg>
      )}
      {src && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          ref={ref}
          src={src}
          alt={alt}
          onLoad={() => setLoaded(true)}
          onError={() => setLoaded(false)}
          style={{ display: loaded ? "block" : "none" }}
        />
      )}
    </>
  );
}
