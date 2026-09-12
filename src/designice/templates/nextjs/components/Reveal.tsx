"use client";

import { useEffect, useRef } from "react";

/**
 * Reveal-on-scroll, done the cheap way.
 *
 * One IntersectionObserver, fired once, toggling a data attribute that CSS
 * animates. It unobserves immediately after firing so scrolling back up does
 * not replay the entrance - re-animating on every pass is the thing that makes
 * a page feel restless rather than alive.
 */
export function Reveal({
  children,
  delay = 0,
  className,
  as: Tag = "div",
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
  as?: React.ElementType;
}) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    // If the element is already on screen at mount (above the fold), show it
    // straight away rather than waiting for a scroll that may never come.
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          node.setAttribute("data-reveal", "shown");
          observer.unobserve(node);
        }
      },
      { threshold: 0.2, rootMargin: "0px 0px -10% 0px" },
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <Tag
      ref={ref}
      data-reveal=""
      style={{ ["--reveal-delay" as string]: `${delay}ms` }}
      className={className}
    >
      {children}
    </Tag>
  );
}
