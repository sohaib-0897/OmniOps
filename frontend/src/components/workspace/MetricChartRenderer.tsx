"use client";

import React from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
} from "recharts";
import { BarChart3, TrendingUp, Calculator, ShieldCheck, FileCheck, Layers } from "lucide-react";
import { EpistemicClaim, Recommendation } from "@/types/api";

export interface MetricDataPoint {
  name: string;
  value: number;
  unit?: string;
  category?: string;
}

interface Props {
  claims: EpistemicClaim[];
  recommendations?: Recommendation[];
}

export function MetricChartRenderer({ claims, recommendations = [] }: Props) {
  const quantitativeData: MetricDataPoint[] = [];

  claims.forEach((claim) => {
    if (claim.epistemic_type === "calculation" && claim.calculation_summary) {
      const match = claim.statement.match(/([+-]?\d+(?:\.\d+)?)\s*(%|USD|\$|k|M|B)?/i);
      if (match) {
        const val = parseFloat(match[1]);
        if (!isNaN(val)) {
          quantitativeData.push({
            name: claim.claim_id,
            value: val,
            unit: match[2] || "",
            category: "Calculation",
          });
        }
      }
    } else {
      const match = claim.statement.match(/(\$|USD)?\s*([+-]?\d+(?:,\d+)*(?:\.\d+)?)\s*(%|USD|\$|k|M|B)?/i);
      if (match && match[2]) {
        const rawNum = match[2].replace(/,/g, "");
        const val = parseFloat(rawNum);
        if (!isNaN(val) && val > 0 && val < 1000000000) {
          quantitativeData.push({
            name: claim.claim_id,
            value: val,
            unit: match[1] || match[3] || "",
            category: claim.epistemic_type,
          });
        }
      }
    }
  });

  const totalClaims = claims.length;
  const factClaims = claims.filter((c) => c.epistemic_type === "fact").length;
  const calcClaims = claims.filter((c) => c.epistemic_type === "calculation").length;
  const measuredConfidence = claims.filter((claim) => claim.confidence_score != null);
  const avgConfidence = measuredConfidence.length
    ? (measuredConfidence.reduce((acc, claim) => acc + (claim.confidence_score as number), 0) / measuredConfidence.length) * 100
    : null;

  return (
    <div className="space-y-3 font-sans">
      {/* 1. Executive Quantitative KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="p-3.5 rounded-xl border border-zinc-800 bg-zinc-950 space-y-1">
          <div className="flex items-center justify-between text-zinc-400 text-[10px] font-bold uppercase tracking-wider">
            <span>Analytical Claims</span>
            <ShieldCheck className="w-3.5 h-3.5 text-zinc-400" />
          </div>
          <p className="text-xl sm:text-2xl font-bold tracking-tight text-white font-mono">{totalClaims}</p>
          <p className="text-[10px] text-zinc-500 font-mono">{factClaims} facts, {calcClaims} calcs</p>
        </div>

        <div className="p-3.5 rounded-xl border border-zinc-800 bg-zinc-950 space-y-1">
          <div className="flex items-center justify-between text-zinc-400 text-[10px] font-bold uppercase tracking-wider">
            <span>Confidence</span>
            <FileCheck className="w-3.5 h-3.5 text-zinc-400" />
          </div>
          <p className="text-xl sm:text-2xl font-bold tracking-tight text-white font-mono">
            {avgConfidence == null ? "N/A" : `${avgConfidence.toFixed(1)}%`}
          </p>
          <p className="text-[10px] text-zinc-500 font-mono">Reference validation</p>
        </div>

        <div className="p-3.5 rounded-xl border border-zinc-800 bg-zinc-950 space-y-1">
          <div className="flex items-center justify-between text-zinc-400 text-[10px] font-bold uppercase tracking-wider">
            <span>Calculations</span>
            <Calculator className="w-3.5 h-3.5 text-zinc-400" />
          </div>
          <p className="text-xl sm:text-2xl font-bold tracking-tight text-white font-mono">{calcClaims}</p>
          <p className="text-[10px] text-zinc-500 font-mono">DuckDB in-memory</p>
        </div>

        <div className="p-3.5 rounded-xl border border-zinc-800 bg-zinc-950 space-y-1">
          <div className="flex items-center justify-between text-zinc-400 text-[10px] font-bold uppercase tracking-wider">
            <span>Actionable Items</span>
            <TrendingUp className="w-3.5 h-3.5 text-zinc-400" />
          </div>
          <p className="text-xl sm:text-2xl font-bold tracking-tight text-white font-mono">{recommendations.length}</p>
          <p className="text-[10px] text-zinc-500 font-mono">Supported strategies</p>
        </div>
      </div>

      {/* 2. Dynamic Chart or Clean Fallback */}
      {quantitativeData.length > 0 ? (
        <div className="border border-zinc-800 bg-zinc-950 rounded-xl p-4 sm:p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-zinc-400" />
              <h4 className="text-xs font-bold text-zinc-200 uppercase tracking-wider">
                Extracted Metric Values Across Claims
              </h4>
            </div>
            <span className="text-[10px] text-zinc-500 font-mono">
              {quantitativeData.length} Data Points
            </span>
          </div>

          <div className="h-48 w-full text-xs">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={quantitativeData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="2 2" stroke="#27272a" vertical={false} />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 10, fill: "#a1a1aa", fontWeight: 600 }}
                  tickLine={false}
                  axisLine={{ stroke: "#3f3f46" }}
                />
                <YAxis
                  tick={{ fontSize: 10, fill: "#a1a1aa", fontWeight: 600 }}
                  tickLine={false}
                  axisLine={{ stroke: "#3f3f46" }}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload as MetricDataPoint;
                      return (
                        <div className="bg-zinc-900 border border-zinc-750 rounded-lg p-2 shadow-2xl text-xs space-y-0.5">
                          <p className="font-bold text-white font-mono">{data.name}</p>
                          <p className="text-zinc-300">
                            Value: <span className="font-mono font-bold text-white">{data.value} {data.unit}</span>
                          </p>
                          <p className="text-[10px] text-zinc-500 capitalize">Category: {data.category}</p>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Bar dataKey="value" radius={[3, 3, 0, 0]}>
                  {quantitativeData.map((entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={index % 2 === 0 ? "#ffffff" : "#a1a1aa"}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : (
        <div className="border border-zinc-800 bg-zinc-950 rounded-xl p-4 text-center space-y-1">
          <div className="flex items-center justify-center gap-1.5 text-xs font-semibold text-zinc-300">
            <Layers className="w-3.5 h-3.5 text-zinc-400" />
            <span>Analytical Findings</span>
          </div>
          <p className="text-xs text-zinc-500">
            Claims shown below have passed reference validation; semantic truth is not automatically guaranteed.
          </p>
        </div>
      )}
    </div>
  );
}
