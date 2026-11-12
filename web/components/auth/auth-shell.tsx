import type { ReactNode } from "react";

// Vertical hairline on each edge of the centered column + a band of
// diagonal stripes behind it - the exact motifs app/page.tsx uses for its
// container rails and section dividers (CTASection, the feature-highlight
// row), reused here so the auth pages read as the same product as the
// landing page instead of a bolted-on shadcn template.
function DiagonalStripeRail() {
  return (
    <div className="relative h-full w-4 shrink-0 overflow-hidden sm:w-6 md:w-8 lg:w-12">
      <div className="absolute top-[-120px] left-[-40px] flex w-[120px] flex-col items-start justify-start sm:left-[-50px] sm:w-[140px] md:left-[-58px] md:w-[162px]">
        {Array.from({ length: 60 }).map((_, i) => (
          <div
            key={i}
            className="h-3 origin-top-left -rotate-45 self-stretch outline outline-[0.5px] outline-offset-[-0.25px] outline-border sm:h-4"
          />
        ))}
      </div>
    </div>
  );
}

export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="relative flex min-h-svh w-full flex-col items-center overflow-x-hidden bg-background">
      <div className="relative flex min-h-svh w-full max-w-none flex-col items-start px-4 sm:px-6 md:px-8 lg:w-[1060px] lg:max-w-[1060px] lg:px-0">
        <div className="absolute top-0 left-4 z-0 h-full w-px bg-border sm:left-6 md:left-8 lg:left-0" />
        <div className="absolute top-0 right-4 z-0 h-full w-px bg-border sm:right-6 md:right-8 lg:right-0" />

        <div className="z-10 flex w-full flex-1 flex-col items-center justify-center px-2 py-12 sm:px-4 md:px-8 lg:px-0">
          <div className="flex w-full items-stretch justify-center border-t border-b border-border">
            <DiagonalStripeRail />
            <div className="flex min-h-[520px] w-full max-w-[460px] flex-col justify-center border-r border-l border-border px-6 py-16 sm:px-12 sm:py-20">
              {children}
            </div>
            <DiagonalStripeRail />
          </div>
        </div>
      </div>
    </div>
  );
}
