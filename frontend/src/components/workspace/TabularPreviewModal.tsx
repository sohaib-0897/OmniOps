"use client";
import { useEffect, useState } from "react";
import { TabularDataset, TablePreview } from "@/types/api";
import { apiClient } from "@/lib/api-client";
import { formatNumber } from "@/lib/utils";
import { Dialog } from "@/components/ui/Dialog";
import { ErrorState, LoadingState } from "@/components/ui/Primitives";

export function TabularPreviewModal({
  table,
  onClose,
}: {
  table: TabularDataset | null;
  onClose: () => void;
}) {
  const [preview, setPreview] = useState<TablePreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let alive = true;
    setPreview(null);
    setQuery("");
    setCopied(false);
    setError(null);
    if (!table) return;
    setLoading(true);
    apiClient
      .get<TablePreview>(
        `/workspaces/${table.workspace_id}/tables/${table.id}/preview`,
      )
      .then((data) => {
        if (alive) setPreview(data);
      })
      .catch((err) => {
        if (alive)
          setError(
            err instanceof Error
              ? err.message
              : "Table preview could not be loaded.",
          );
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [table, retry]);
  const copy = async () => {
    if (!preview) return;
    try {
      await navigator.clipboard.writeText(preview.columns.join(", "));
      setCopied(true);
    } catch {
      setError(
        "Copy is unavailable. Select the column names and copy them manually.",
      );
    }
  };
  const columns =
    preview?.schema_definition.filter((column) =>
      column.name.toLowerCase().includes(query.toLowerCase()),
    ) || [];
  return (
    <Dialog
      open={Boolean(table)}
      onClose={onClose}
      title={table?.table_name || "Table preview"}
      description={
        table
          ? `${table.row_count.toLocaleString()} rows · ${table.column_count} columns`
          : undefined
      }
    >
      {loading ? (
        <LoadingState label="Loading table preview" />
      ) : error ? (
        <ErrorState
          message={error}
          onRetry={() => setRetry((value) => value + 1)}
        />
      ) : (
        preview && (
          <div className="space-y-6">
            <section>
              <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                <h3 className="section-title">Column profile</h3>
                <button className="btn-secondary" onClick={() => void copy()}>
                  {copied ? "Copied" : "Copy column names"}
                </button>
              </div>
              <input
                aria-label="Filter columns"
                placeholder="Filter columns"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="field mb-3"
              />
              <div className="overflow-x-auto rounded-md border border-zinc-800">
                <table className="data-table whitespace-nowrap">
                  <caption className="sr-only">
                    Column types, missing values and unique values
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Column</th>
                      <th scope="col">Type</th>
                      <th scope="col" className="text-right">
                        Null %
                      </th>
                      <th scope="col" className="text-right">
                        Unique
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {columns.map((column) => (
                      <tr key={column.name}>
                        <th scope="row" className="font-mono">
                          {column.name}
                        </th>
                        <td className="font-mono">{column.type}</td>
                        <td className="text-right font-mono">
                          {column.null_percentage == null
                            ? "—"
                            : `${formatNumber(column.null_percentage)}%`}
                        </td>
                        <td className="text-right font-mono">
                          {column.unique_count == null
                            ? "—"
                            : formatNumber(column.unique_count)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {columns.length === 0 && (
                  <p className="meta-copy p-4">No columns match your search.</p>
                )}
              </div>
            </section>
            <section>
              <h3 className="section-title mb-3">
                Sample rows · {preview.sample_rows.length}
              </h3>
              <div
                tabIndex={0}
                role="region"
                aria-label="Scrollable sample table"
                className="max-h-80 overflow-auto rounded-md border border-zinc-800"
              >
                <table className="data-table whitespace-nowrap">
                  <thead className="sticky top-0">
                    <tr>
                      {preview.columns.map((column) => (
                        <th key={column} scope="col">
                          {column}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.sample_rows.map((row, index) => (
                      <tr key={index}>
                        {preview.columns.map((column) => (
                          <td
                            key={column}
                            className={
                              typeof row[column] === "number"
                                ? "text-right font-mono"
                                : ""
                            }
                          >
                            {row[column] == null ? (
                              <span className="text-zinc-400">null</span>
                            ) : typeof row[column] === "number" ? (
                              formatNumber(row[column])
                            ) : (
                              String(row[column])
                            )}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {preview.sample_rows.length === 0 && (
                  <p className="meta-copy p-4">No sample rows available.</p>
                )}
              </div>
            </section>
          </div>
        )
      )}
    </Dialog>
  );
}
