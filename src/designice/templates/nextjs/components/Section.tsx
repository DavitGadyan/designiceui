import type { ReactNode } from "react";

/**
 * The vertical rhythm of the whole site lives here.
 *
 * Sections vary by `tone` rather than by ad-hoc padding, because the fastest
 * way to make a page look generated is eleven identical slabs stacked in a
 * column. Alternating the ground colour is the cheapest way to break that.
 */
export function Section({
  children,
  id,
  tone = "ground",
  className = "",
}: {
  children: ReactNode;
  id?: string;
  tone?: "ground" | "surface";
  className?: string;
}) {
  return (
    <section
      id={id}
      className={`section-pad px-6 md:px-10 ${className}`}
      style={{
        background: tone === "surface" ? "var(--color-surface)" : "var(--color-ground)",
      }}
    >
      <div className="mx-auto w-full max-w-[1200px]">{children}</div>
    </section>
  );
}
