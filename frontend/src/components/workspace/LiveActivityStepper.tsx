"use client";
import { useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertCircle,
  Bookmark,
  Check,
  Circle,
  Square,
  Wrench,
} from "lucide-react";
import { InvestigationStreamState } from "@/hooks/useInvestigationStream";
import { StatusBadge } from "@/components/ui/Primitives";
import { formatDuration } from "@/lib/utils";

const pretty = (value: string) =>
  value.replace(/[._]/g, " ").replace(/^\w/, (letter) => letter.toUpperCase());
// Only operational identifiers and status fields are exposed, never reasoning/tool payloads.
const detailKeys = [
  "step_id",
  "task_id",
  "tool",
  "status",
  "from",
  "to",
  "correlation_id",
  "request_id",
  "plan_version",
  "duration_ms",
  "failure_code",
];
export function LiveActivityStepper({
  streamState,
  onCancel,
}: {
  streamState: InvestigationStreamState;
  onCancel: () => void;
}) {
  const [visible, setVisible] = useState(50);
  const events = useRef<HTMLOListElement>(null);
  const seen = useRef(new Set<string>());
  const mountedAt = useRef(Date.now());
  const wasLive = useRef(false);
  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    for (const event of streamState.timeline) {
      if (!seen.current.has(event.id) && wasLive.current && streamState.connection === "live" && event.timestamp && Date.parse(event.timestamp) > mountedAt.current && !reduced) {
        const row = Array.from(events.current?.children || []).find(element => (element as HTMLElement).dataset.eventId === event.id);
        row?.animate([{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "none" }], { duration: 200, easing: "cubic-bezier(0.22, 1, 0.36, 1)" });
      }
      seen.current.add(event.id);
    }
    wasLive.current = streamState.connection === "live";
  }, [streamState.timeline, streamState.connection]);
  const active = [
    "created",
    "planning",
    "ready",
    "running",
    "executing",
    "observing",
    "verifying",
    "replanning",
    "synthesizing",
  ].includes(streamState.status);
  const timeline = streamState.timeline;
  return (
    <div className="space-y-5">
      <section className="surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="section-title flex items-center gap-2">
            <Activity className="h-4 w-4 text-zinc-400" />
            Runtime trace
          </h2>
          <StatusBadge status={streamState.status} />
        </div>
        <div className="mt-3 flex items-center justify-between gap-2">
          <span role="status" className="text-[11px] text-zinc-400">
            {streamState.connection === "live"
              ? "Live connection"
              : streamState.connection === "reconnecting"
                ? "Reconnecting · history preserved"
                : streamState.connection === "connecting"
                  ? "Connecting"
                  : streamState.connection === "offline"
                    ? "Offline · retrying"
                    : "Persisted history"}
          </span>
          {active && (
            <button className="btn-destructive h-7 px-2" onClick={onCancel}>
              <Square className="h-3 w-3" />
              Cancel
            </button>
          )}
        </div>
        {streamState.activitySummary && (
          <p className="mt-4 border-t border-zinc-800 pt-3 text-xs leading-6 text-zinc-300">
            {streamState.activitySummary}
          </p>
        )}
      </section>
      {streamState.planTasks.length > 0 && (
        <details open className="surface p-4">
          <summary className="section-title">
            Plan · {streamState.planTasks.length} steps
          </summary>
          <ol className="mt-4 divide-y divide-zinc-800">
            {streamState.planTasks.map((task, index) => (
              <li key={task.id} className="flex gap-3 py-3 first:pt-0">
                <span className="mono-copy mt-0.5">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div className="min-w-0">
                  <p className="text-xs leading-6 text-zinc-200">
                    {task.title}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <StatusBadge status={task.status || "pending"} />
                    {task.target_modality && (
                      <span className="meta-copy capitalize">
                        {task.target_modality}
                      </span>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </details>
      )}
      {streamState.steps.length > 0 && (
        <details className="surface p-4">
          <summary className="section-title">
            Recorded operations · {streamState.steps.length}
          </summary>
          <ol className="mt-4 space-y-4">
            {streamState.steps.map((step) => (
              <li key={step.id}>
                <p className="text-xs leading-6 text-zinc-300">
                  {step.user_activity_summary || pretty(step.step_type)}
                </p>
                <p className="mono-copy mt-1">
                  {step.tool_name || pretty(step.step_type)} ·{" "}
                  {formatDuration(step.duration_ms)}
                </p>
              </li>
            ))}
          </ol>
        </details>
      )}
      {streamState.evidenceDiscovered.length > 0 && (
        <details className="surface p-4" open>
          <summary className="section-title">
            Observed evidence · {streamState.evidenceDiscovered.length}
          </summary>
          <div className="mt-4 space-y-4">
            {streamState.evidenceDiscovered.map((item) => (
              <article
                key={item.citation_id}
                className="border-l border-zinc-600 pl-3"
              >
                <h3 className="break-words text-xs font-medium">
                  {item.source_name}
                </h3>
                <p className="mt-1 text-[11px] capitalize text-zinc-400">
                  {item.modality} · Observation
                </p>
                <p className="mt-2 text-xs leading-6 text-zinc-300">
                  {item.quote}
                </p>
              </article>
            ))}
          </div>
        </details>
      )}
      <section className="surface p-4">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="section-title">Lifecycle events</h2>
          <span className="mono-copy">{timeline.length}</span>
        </div>
        {timeline.length === 0 ? (
          <p className="meta-copy py-3">
            Start an investigation to see persisted operational events here.
          </p>
        ) : (
          <ol ref={events} className="divide-y divide-zinc-800">
            {timeline.slice(-visible).map((event) => {
              const Icon = event.type.includes("failed")
                ? AlertCircle
                : event.type.includes("completed") ||
                    event.type.includes("verified")
                  ? Check
                  : event.type.includes("tool")
                    ? Wrench
                    : event.type.includes("observation")
                      ? Bookmark
                      : Circle;
              return (
                <li key={event.id} data-event-id={event.id} className="py-3">
                  <details>
                    <summary className="flex list-none items-start gap-2">
                      <Icon
                        className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${event.type.includes("failed") ? "text-red-300" : "text-zinc-400"}`}
                      />
                      <span className="min-w-0 flex-1">
                        <span className="block text-xs leading-5 text-zinc-200">
                          {pretty(event.type)}
                        </span>
                        {event.timestamp && (
                          <time
                            title={new Date(event.timestamp).toLocaleString()}
                            className="mt-1 block font-mono text-[11px] text-zinc-400"
                          >
                            {new Date(event.timestamp).toLocaleTimeString([], {
                              hour: "2-digit",
                              minute: "2-digit",
                              second: "2-digit",
                            })}
                          </time>
                        )}
                      </span>
                      <span className="text-zinc-500" aria-hidden="true">
                        +
                      </span>
                    </summary>
                    <dl className="mt-3 space-y-2 border-l border-zinc-700 pl-3 text-[11px] text-zinc-400">
                      <div>
                        <dt>Event ID</dt>
                        <dd className="mt-1 break-all font-mono">{event.id}</dd>
                      </div>
                      {detailKeys
                        .filter(
                          (key) =>
                            event.payload?.[key] != null &&
                            ["string", "number", "boolean"].includes(
                              typeof event.payload[key],
                            ),
                        )
                        .map((key) => (
                          <div key={key}>
                            <dt>{pretty(key)}</dt>
                            <dd className="mt-1 break-all font-mono">
                              {String(event.payload![key])}
                            </dd>
                          </div>
                        ))}
                    </dl>
                  </details>
                </li>
              );
            })}
          </ol>
        )}
        {timeline.length > visible && (
          <button
            className="btn-secondary mt-3 w-full"
            onClick={() => setVisible((count) => count + 50)}
          >
            Show earlier events ({timeline.length - visible})
          </button>
        )}
      </section>
    </div>
  );
}
