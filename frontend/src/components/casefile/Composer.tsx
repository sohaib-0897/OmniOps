"use client";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
  type KeyboardEvent,
} from "react";
import { ArrowUp, FileText, Loader2, Paperclip, X } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { formatBytes } from "@/lib/utils";

export const ALLOWED_EXTENSIONS = [
  ".pdf", ".docx", ".xlsx", ".xls", ".csv", ".tsv", ".mp3", ".wav", ".m4a", ".ogg", ".png", ".jpg", ".jpeg", ".txt",
];

interface Attachment {
  id: string;
  file: File;
  status: "ready" | "uploading" | "uploaded" | "failed";
  error?: string;
}

export interface ComposerHandle {
  setObjective: (value: string) => void;
  focus: () => void;
}

interface Props {
  workspaceId: string;
  onStart: (objective: string) => Promise<boolean>;
  onSourcesChanged: () => void;
  submitting?: boolean;
  scopeLabel: string;
  scopeEmpty?: boolean;
  placeholder?: string;
  canEdit?: boolean;
}

/** The only element with the 22 px composer radius. */
export const Composer = forwardRef<ComposerHandle, Props>(function Composer(
  { workspaceId, onStart, onSourcesChanged, submitting = false, scopeLabel, scopeEmpty, placeholder = "Ask about your sources…", canEdit = true },
  handle,
) {
  const [objective, setObjective] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const busy = working || submitting;

  useImperativeHandle(handle, () => ({
    setObjective: (value: string) => {
      setObjective(value);
      textarea.current?.focus();
    },
    focus: () => textarea.current?.focus(),
  }));

  useEffect(() => {
    const field = textarea.current;
    if (!field) return;
    field.style.height = "auto";
    field.style.height = `${Math.min(field.scrollHeight, 280)}px`;
  }, [objective]);

  const selectFiles = (event: ChangeEvent<HTMLInputElement>) => {
    const incoming = Array.from(event.target.files || []).map((file, index): Attachment => {
      const extension = `.${file.name.split(".").pop()?.toLowerCase() || ""}`;
      const invalid =
        file.size > 50 * 1024 * 1024
          ? "Choose a file smaller than 50 MB."
          : !ALLOWED_EXTENSIONS.includes(extension)
            ? "This file format is not supported."
            : undefined;
      return { id: `${file.name}:${file.size}:${file.lastModified}:${index}`, file, status: invalid ? "failed" : "ready", error: invalid };
    });
    setAttachments((current) => [...current, ...incoming]);
    setError(null);
    event.target.value = "";
  };

  const update = (id: string, change: Partial<Attachment>) =>
    setAttachments((items) => items.map((item) => (item.id === id ? { ...item, ...change } : item)));

  const run = async () => {
    if (!objective.trim() || busy) return;
    if (objective.trim().length < 5) {
      setError("Ask a question of at least five characters.");
      return;
    }
    if (attachments.some((item) => item.status === "failed")) {
      setError("Remove files with errors before starting the investigation.");
      return;
    }
    setWorking(true);
    setError(null);
    try {
      for (const attachment of attachments.filter((item) => item.status !== "uploaded")) {
        update(attachment.id, { status: "uploading", error: undefined });
        try {
          const form = new FormData();
          form.append("file", attachment.file);
          await apiClient.post(`/workspaces/${workspaceId}/files`, form);
          update(attachment.id, { status: "uploaded" });
          onSourcesChanged();
        } catch (uploadError) {
          const message = uploadError instanceof Error ? uploadError.message : "The source could not be uploaded.";
          update(attachment.id, { status: "failed", error: message });
          throw new Error(message);
        }
      }
      if (await onStart(objective.trim())) {
        setObjective("");
        setAttachments([]);
      }
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : "The investigation could not be started.");
    } finally {
      setWorking(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void run();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void run();
    }
  };

  return (
    <form onSubmit={submit} aria-label="Start an investigation">
      <div className="composer">
        {attachments.length > 0 && (
          <div className="flex flex-wrap gap-2 border-b border-line px-4 py-3" aria-label="Attached files">
            {attachments.map((attachment) => (
              <span key={attachment.id} className={`attachment-chip ${attachment.status === "failed" ? "attachment-chip-error" : ""}`} title={attachment.error || attachment.file.name}>
                {attachment.status === "uploading" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileText className="h-3.5 w-3.5" />}
                <span className="max-w-48 truncate">{attachment.file.name}</span>
                <span className="text-ink-3">{formatBytes(attachment.file.size, 1)}</span>
                {!busy && (
                  <button type="button" aria-label={`Remove ${attachment.file.name}`} onClick={() => setAttachments((items) => items.filter((item) => item.id !== attachment.id))} className="rounded-sm text-ink-3 hover:text-ink">
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </span>
            ))}
          </div>
        )}
        <label htmlFor="objective-input" className="sr-only">Investigation question</label>
        <textarea
          ref={textarea}
          id="objective-input"
          value={objective}
          onChange={(event) => setObjective(event.target.value)}
          onKeyDown={onKeyDown}
          disabled={busy || !canEdit}
          rows={1}
          placeholder={canEdit ? placeholder : "Viewers can read investigations but not start them."}
          aria-describedby="composer-scope"
        />
        <div className="flex items-center gap-2 px-5 pb-[18px] pt-[18px]">
          <span id="composer-scope" className="scope-chip" data-empty={scopeEmpty || undefined}>{scopeLabel}</span>
          <span className="flex-1" />
          <input ref={fileInput} type="file" multiple hidden accept={ALLOWED_EXTENSIONS.join(",")} onChange={selectFiles} aria-label="Attach source files" />
          <button type="button" className="btn-icon" disabled={busy || !canEdit} aria-label="Attach source files" onClick={() => fileInput.current?.click()}>
            <Paperclip className="h-4 w-4" aria-hidden="true" />
          </button>
          <span className="t-meta hidden text-ink-3 sm:inline" aria-hidden="true">↵</span>
          <button type="submit" className="send-button" disabled={busy || !objective.trim() || !canEdit} aria-label={busy ? "Starting investigation" : "Start investigation"}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}
          </button>
        </div>
      </div>
      <p className="sr-only" role="status">{busy ? "Starting investigation" : ""}</p>
      {error && <p role="alert" className="t-meta mt-2 text-critical">{error}</p>}
    </form>
  );
});
