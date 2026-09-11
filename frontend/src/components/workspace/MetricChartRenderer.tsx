import { EpistemicClaim, Recommendation } from "@/types/api";

/** Counts only: prose is not a quantitative series with comparable units. */
export function MetricChartRenderer({
  claims,
  recommendations = [],
}: {
  claims: EpistemicClaim[];
  recommendations?: Recommendation[];
}) {
  const values = [
    ["Claims", claims.length],
    [
      "Verified references",
      claims.filter((claim) => claim.verification_status === "VERIFIED").length,
    ],
    [
      "Calculations",
      claims.filter((claim) => claim.epistemic_type === "calculation").length,
    ],
    ["Recommendations", recommendations.length],
  ] as const;
  return (
    <dl className="grid grid-cols-2 gap-y-4 border-y border-zinc-800 py-4 sm:grid-cols-4">
      {values.map(([label, value]) => (
        <div key={label} className="border-zinc-800 px-3 odd:border-r sm:border-r sm:last:border-r-0">
          <dt className="text-[11px] text-zinc-400">{label}</dt>
          <dd className="mt-1.5 text-xl font-medium">
            {value.toLocaleString()}
          </dd>
        </div>
      ))}
    </dl>
  );
}
