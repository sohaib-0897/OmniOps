"use client";

import { useEffect, useState, type RefObject } from "react";

/**
 * "The pull": a thread from the clicked citation marker to its passage in the
 * inspector. Decorative only (aria-hidden); the relationship is stated in text
 * in the inspector. Drawn only when the inspector sits beside the brief.
 */
export function PullThread({
  anchorId,
  target,
  version,
}: {
  anchorId: string | null | undefined;
  target: RefObject<HTMLElement>;
  version: string;
}) {
  const [geometry, setGeometry] = useState<{ d: string; x: number; y: number; length: number } | null>(null);

  useEffect(() => {
    if (!anchorId) {
      setGeometry(null);
      return;
    }
    let frame = 0;
    const measure = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const anchor = document.getElementById(anchorId);
        const passage = target.current;
        if (!anchor || !passage || window.innerWidth < 1200) {
          setGeometry(null);
          return;
        }
        const a = anchor.getBoundingClientRect();
        const p = passage.getBoundingClientRect();
        const visible = (rect: DOMRect) => rect.bottom > 0 && rect.top < window.innerHeight && rect.width > 0;
        if (!visible(a) || !visible(p)) {
          setGeometry(null);
          return;
        }
        const y1 = a.top + a.height / 2;
        // Start after any markers that follow on the same line so the run never strikes through them.
        let x1 = a.right;
        for (let next = anchor.nextElementSibling; next?.classList.contains("cite"); next = next.nextElementSibling) {
          const r = next.getBoundingClientRect();
          if (Math.abs(r.top + r.height / 2 - y1) > a.height / 2) break;
          x1 = Math.max(x1, r.right);
        }
        const x2 = p.left - 2;
        const y2 = Math.min(Math.max(p.top + 18, y1 - 400), p.bottom - 12);
        // Markers end their line, so run along it to the block edge and curve only in the gutter (Figma B08).
        const block = anchor.closest(".finding, .action-row, .brief-col");
        const edge = Math.min(Math.max(x1, block ? block.getBoundingClientRect().right : x1), x2 - 24);
        const mid = (edge + x2) / 2;
        const d = `M${x1.toFixed(1)} ${y1.toFixed(1)} L ${edge.toFixed(1)} ${y1.toFixed(1)} C ${mid.toFixed(1)} ${y1.toFixed(1)}, ${mid.toFixed(1)} ${y2.toFixed(1)}, ${x2.toFixed(1)} ${y2.toFixed(1)}`;
        const length = (edge - x1) + Math.hypot(x2 - edge, y2 - y1) * 1.3;
        setGeometry({ d, x: x2, y: y2, length });
      });
    };
    // Let the inspector finish sliding in before the first measurement.
    const settle = window.setTimeout(measure, 230);
    measure();
    window.addEventListener("resize", measure);
    document.addEventListener("scroll", measure, true);
    return () => {
      window.clearTimeout(settle);
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", measure);
      document.removeEventListener("scroll", measure, true);
    };
  }, [anchorId, target, version]);

  if (!geometry) return null;
  return (
    <svg className="pull-thread" aria-hidden="true" width="100%" height="100%">
      <path key={version} d={geometry.d} style={{ ["--len" as string]: Math.ceil(geometry.length) }} />
      <circle cx={geometry.x} cy={geometry.y} r="3" />
    </svg>
  );
}
