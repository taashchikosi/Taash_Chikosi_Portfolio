/**
 * Fixed, subtle depth layer behind all content: a faint masked grid + a soft
 * green glow at the top. Keeps the flat near-black from reading as "empty".
 */
export function SiteBackground() {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 -z-10 overflow-hidden"
    >
      <div className="absolute inset-0 bg-grid [mask-image:radial-gradient(ellipse_70%_45%_at_50%_0%,black,transparent)]" />
      <div className="absolute left-1/2 top-[-220px] h-[520px] w-[820px] -translate-x-1/2 rounded-full bg-accent/10 blur-[130px]" />
    </div>
  );
}
