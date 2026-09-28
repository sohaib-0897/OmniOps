/** Shared motion decisions for the product and public story. Times are seconds. */
export const motionTokens = {
  quick: 0.16,
  panel: 0.26,
  narrative: 0.62,
  ease: [0.22, 1, 0.36, 1] as [number, number, number, number],
  spring: { type: "spring" as const, stiffness: 380, damping: 32, mass: 0.85 },
  stagger: 0.055,
};

export const reducedMotionQuery = "(prefers-reduced-motion: reduce)";
