// Same pill-shaped primary CTA markup as the landing page's hero/CTA
// buttons (app/page.tsx, components/landing/cta-section.tsx) - a plain
// <button> rather than the shared ui/Button, since that CTA treatment
// (rounded-full, inset highlight, gradient overlay) is a marketing-page
// motif, not the default button used throughout the rest of the app.
export function SubmitButton({
  pending,
  children,
}: {
  pending: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="submit"
      disabled={pending}
      className="relative flex h-10 w-full items-center justify-center overflow-hidden rounded-full bg-primary py-[6px] shadow-[0px_0px_0px_2.5px_rgba(255,255,255,0.08)_inset] transition-opacity outline-none hover:opacity-90 focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50"
    >
      <div className="absolute top-0 left-0 h-10 w-44 bg-gradient-to-b from-[rgba(255,255,255,0)] to-[rgba(0,0,0,0.10)] mix-blend-multiply" />
      <span className="text-sm font-medium text-primary-foreground">{children}</span>
    </button>
  );
}
