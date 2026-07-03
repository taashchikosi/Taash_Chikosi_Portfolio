import { SITE } from "@/lib/site";

export function SiteFooter() {
  return (
    <footer>
      <div className="wrap foot">
        <span>© 2026 {SITE.name}</span>
        <span>{SITE.domain}</span>
      </div>
    </footer>
  );
}
