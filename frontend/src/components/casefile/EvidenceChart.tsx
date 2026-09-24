"use client";

import { useId } from "react";
import type { ChartSpec } from "@/lib/brief-model";
import { formatNumber } from "@/lib/utils";

const ORDINAL = /^(q[1-4]|fy\s?\d{2,4}|\d{4}(-\d{2}){0,2}|(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*)\b/i;

function niceBounds(min: number, max: number) {
  if (min === max) return { low: min - 1, high: max + 1 };
  const span = max - min;
  const step = Math.pow(10, Math.floor(Math.log10(span))) / 2;
  return { low: Math.floor(min / step) * step, high: Math.ceil(max / step) * step };
}

/**
 * Plots exactly the saved rows of an SQL calculation cited by a verified claim.
 * Ordered labels draw a line; categories draw bars from zero. Any axis that
 * does not start at zero says so.
 */
export function EvidenceChart({
  chart,
  onInspect,
}: {
  chart: ChartSpec;
  onInspect: () => void;
}) {
  const titleId = useId();
  const values = chart.rows.map((row) => row.value);
  const ordered = chart.rows.length >= 3 && chart.rows.every((row) => ORDINAL.test(row.label.trim()));
  const width = 568;
  const height = 110;
  const left = 44;
  const right = 12;
  const top = 18;
  const bottom = 22;
  const plotW = width - left - right;
  const plotH = height - top - bottom;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const bounds = ordered ? niceBounds(min, max) : { low: Math.min(0, min), high: Math.max(0, max) || 1 };
  const y = (value: number) => top + plotH - ((value - bounds.low) / (bounds.high - bounds.low || 1)) * plotH;
  const step = chart.rows.length > 1 ? plotW / (chart.rows.length - (ordered ? 1 : 0)) : plotW;
  const x = (index: number) => left + (ordered ? index * step : index * step + step / 2);
  const hash = chart.calculation.hash ? `${chart.calculation.hash.slice(0, 4)}…${chart.calculation.hash.slice(-3)}` : "not recorded";
  const nonZero = bounds.low !== 0;
  const linePath = chart.rows.map((row, index) => `${index ? "L" : "M"}${x(index).toFixed(1)} ${y(row.value).toFixed(1)}`).join(" ");

  return (
    <figure className="chart-card fold-section" aria-labelledby={titleId}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <figcaption id={titleId} className="t-label text-ink">
            {chart.valueKey} by {chart.labelKey}
          </figcaption>
          <p className="t-meta mt-0.5 flex flex-wrap items-center gap-x-2 text-ink-3">
            <span>SQL calculation · query and output in the inspector · hash {hash}</span>
            <button type="button" className="calc-marker" onClick={onInspect} aria-label={`Open calculation ƒ${chart.calcNumber} in the inspector`}>
              ƒ{chart.calcNumber}
            </button>
          </p>
        </div>
        {nonZero && <span className="t-meta shrink-0 text-[11px] text-ink-3">Axis starts at {formatNumber(bounds.low)}</span>}
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label={`${chart.valueKey} by ${chart.labelKey}: ${chart.rows.map((row) => `${row.label} ${formatNumber(row.value)}`).join(", ")}`} className="mt-2 block overflow-visible">
        <line x1={left} x2={width - right} y1={top} y2={top} stroke="var(--line)" />
        <line x1={left} x2={width - right} y1={top + plotH} y2={top + plotH} stroke="var(--line)" />
        <text x={0} y={top + 4} fontSize="11" fill="var(--ink-3)">{formatNumber(bounds.high)}</text>
        <text x={0} y={top + plotH + 4} fontSize="11" fill="var(--ink-3)">{formatNumber(bounds.low)}</text>
        {ordered ? (
          <>
            <path d={linePath} fill="none" stroke="var(--provenance)" strokeWidth="1.5" className="chart-series" />
            {chart.rows.map((row, index) => (
              <g key={index}>
                <circle cx={x(index)} cy={y(row.value)} r="3.5" fill="var(--provenance)" stroke="var(--surface)" strokeWidth="1" />
                <text x={x(index)} y={y(row.value) - 8} textAnchor="middle" fontSize="12" fontWeight="500" fill="var(--ink)">{formatNumber(row.value)}</text>
              </g>
            ))}
          </>
        ) : (
          chart.rows.map((row, index) => {
            const barW = Math.max(6, Math.min(40, step * 0.6));
            const top0 = Math.min(y(row.value), y(0));
            return (
              <g key={index}>
                <rect x={x(index) - barW / 2} y={top0} width={barW} height={Math.max(1, Math.abs(y(row.value) - y(0)))} rx="2" fill="var(--provenance)" />
                <text x={x(index)} y={top0 - 6} textAnchor="middle" fontSize="12" fontWeight="500" fill="var(--ink)">{formatNumber(row.value)}</text>
              </g>
            );
          })
        )}
        {chart.rows.map((row, index) => (
          <text key={`l${index}`} x={x(index)} y={height - 4} textAnchor="middle" fontSize="12" fill="var(--ink-3)">
            {row.label.length > 12 ? `${row.label.slice(0, 11)}…` : row.label}
          </text>
        ))}
      </svg>
    </figure>
  );
}
