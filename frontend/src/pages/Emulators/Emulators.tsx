import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { apiFetch, ApiError } from "@/api/client";
import TopBar from "@/components/layout/TopBar";
import { EMULATOR_ERA_MAP, ERA_COLOR } from "@/types/era";
import { useToast } from "@/ui/ToastProvider";
import type { components } from "@shared/types";
type CatalogEntry = components["schemas"]["CatalogEntryResponse"];

function initials(name: string) {
  return name.slice(0, 2).toUpperCase();
}

function EmulatorCard({
  entry,
  onClick,
  editing,
  editPath,
  onEditPathChange,
  onEdit,
  onSave,
  onCancelEdit,
  onDelete,
  saving,
}: {
  entry: CatalogEntry;
  onClick: () => void;
  editing: boolean;
  editPath: string;
  onEditPathChange: (v: string) => void;
  onEdit: () => void;
  onSave: () => void;
  onCancelEdit: () => void;
  onDelete: () => void;
  saving: boolean;
}) {
  const eras = EMULATOR_ERA_MAP[entry.slug] ?? [];
  const isReady = entry.is_installed && entry.install_path;
  const canEdit = false;

  return (
    <div
      className="rounded-lg w-full"
      style={{
        background: "rgb(var(--surface-1))",
        border: "1px solid rgb(var(--border))",
      }}
    >
      {/* Main content — click navigates to detail */}
      <div
        className="p-[18px] cursor-pointer transition-colors duration-[120ms]"
        onClick={onClick}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLDivElement).style.background =
            "rgb(var(--surface-2))";
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLDivElement).style.background = "transparent";
        }}
      >
        <div className="flex items-start gap-3.5">
          <div
            className="flex shrink-0 items-center justify-center rounded-xl"
            style={{
              width: 52,
              height: 52,
              background: "rgb(var(--surface-2))",
              border: "1px solid rgb(var(--border-strong))",
              fontFamily: "var(--font-mono)",
              fontWeight: 700,
              fontSize: '1.25rem',
              color: "rgb(var(--peach-300))",
            }}
          >
            {initials(entry.name)}
          </div>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2.5 mb-1.5">
              <span
                style={{
                  fontFamily: "var(--font-display)",
                  fontWeight: 600,
                  fontSize: '1.125rem',
                  lineHeight: 1,
                  color: "rgb(var(--fg-1))",
                }}
              >
                {entry.name}
              </span>
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: '0.75rem',
                  color: "rgb(var(--fg-3))",
                }}
              >
                {entry.version}
              </span>
              <span style={{ flex: 1 }} />
              <span
                className="inline-flex items-center gap-1.5"
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: '0.6875rem',
                  fontWeight: 500,
                  color: isReady ? "rgb(var(--success))" : "rgb(var(--error))",
                }}
              >
                <span
                  className="rounded-full inline-block"
                  style={{
                    width: 6,
                    height: 6,
                    background: isReady ? "rgb(var(--success))" : "rgb(var(--error))",
                  }}
                />
                {isReady ? "Ready" : "Not installed"}
              </span>
            </div>

            <div
              style={{
                fontFamily: "var(--font-display)",
                fontSize: '0.8125rem',
                lineHeight: 1.4,
                color: "rgb(var(--fg-2))",
                marginBottom: 12,
              }}
            >
              {entry.description}
            </div>

            {eras.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-3.5">
                {eras.map((era) => (
                  <span
                    key={era}
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontWeight: 600,
                      fontSize: '0.6875rem',
                      letterSpacing: "0.08em",
                      padding: "4px 6px",
                      borderRadius: "var(--r-1)",
                      border: `1px solid ${ERA_COLOR[era] ?? "rgb(var(--border))"}`,
                      color: ERA_COLOR[era] ?? "rgb(var(--fg-3))",
                      display: "inline-block",
                    }}
                  >
                    {era}
                  </span>
                ))}
              </div>
            )}

            <div
              className="flex gap-[18px] pt-3"
              style={{
                borderTop: "1px solid rgb(var(--border))",
                fontFamily: "var(--font-mono)",
                fontSize: '0.75rem',
                fontWeight: 500,
                color: "rgb(var(--fg-3))",
              }}
            >
              <span>
                <strong style={{ color: "rgb(var(--fg-1))", marginRight: 4 }}>
                  {entry.install_type === "rom_pack"
                    ? "—"
                    : entry.is_installed
                      ? "✓"
                      : "○"}
                </strong>
                {entry.install_type}
              </span>
              {entry.license && (
                <span>
                  <strong style={{ color: "rgb(var(--fg-1))", marginRight: 4 }}>
                    {entry.license}
                  </strong>
                  license
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Inline edit / action bar */}
      {editing ? (
        <div
          className="px-[18px] pb-[14px] pt-3 flex gap-2 items-center"
          style={{ borderTop: "1px solid rgb(var(--border))" }}
        >
          <input
            value={editPath}
            onChange={(e) => onEditPathChange(e.target.value)}
            placeholder="Path to executable"
            autoFocus
            style={{
              flex: 1,
              background: "rgb(var(--surface-2))",
              border: "1px solid rgb(var(--border))",
              borderRadius: "var(--r-2)",
              padding: "7px 10px",
              fontFamily: "var(--font-mono)",
              fontSize: '0.75rem',
              color: "rgb(var(--fg-1))",
              outline: "none",
            }}
          />
          <button
            type="button"
            onClick={onSave}
            disabled={saving}
            style={{
              border: "none",
              fontFamily: "var(--font-display)",
              fontSize: '0.8125rem',
              fontWeight: 600,
              padding: "7px 12px",
              borderRadius: "var(--r-2)",
              cursor: saving ? "not-allowed" : "pointer",
              background: "rgb(var(--peach-500))",
              color: "rgb(var(--accent-ink))",
              opacity: saving ? 0.6 : 1,
            }}
          >
            {saving ? "Saving…" : "Save"}
          </button>
          <button
            type="button"
            onClick={onCancelEdit}
            style={{
              border: "1px solid rgb(var(--border))",
              fontFamily: "var(--font-display)",
              fontSize: '0.8125rem',
              fontWeight: 500,
              padding: "7px 12px",
              borderRadius: "var(--r-2)",
              cursor: "pointer",
              background: "transparent",
              color: "rgb(var(--fg-2))",
            }}
          >
            Cancel
          </button>
        </div>
      ) : (
        <div
          className="px-[18px] py-2.5 flex gap-2 justify-end items-center"
          style={{ borderTop: "1px solid rgb(var(--border))" }}
        >
          {canEdit && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onEdit();
              }}
              style={{
                border: "1px solid rgb(var(--border))",
                fontFamily: "var(--font-display)",
                fontSize: '0.75rem',
                fontWeight: 500,
                padding: "5px 10px",
                borderRadius: "var(--r-2)",
                cursor: "pointer",
                background: "transparent",
                color: "rgb(var(--fg-3))",
              }}
            >
              Edit path
            </button>
          )}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            style={{
              border: "1px solid rgb(var(--error))",
              fontFamily: "var(--font-display)",
              fontSize: '0.75rem',
              fontWeight: 500,
              padding: "5px 10px",
              borderRadius: "var(--r-2)",
              cursor: "pointer",
              background: "transparent",
              color: "rgb(var(--error))",
            }}
          >
            Remove
          </button>
        </div>
      )}
    </div>
  );
}

export default function Emulators() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [editingSlug, setEditingSlug] = useState<string | null>(null);
  const [editPath, setEditPath] = useState("");
  const [saving, setSaving] = useState(false);

  const { data: catalog = [], isLoading } = useQuery<CatalogEntry[]>({
    queryKey: ["emulators-catalog"],
    queryFn: () => apiFetch<CatalogEntry[]>("/api/v1/emulator-items"),
    staleTime: 10_000,
  });

  const emulatorEntries = catalog.filter((e) => e.install_type !== "rom_pack");
  const installedCount = emulatorEntries.filter((e) => e.is_installed).length;

  function handleStartEdit(entry: CatalogEntry) {
    setEditingSlug(entry.slug);
    setEditPath(entry.install_path ?? "");
  }

  async function handleSavePath(_slug: string) {
    setSaving(true);
    try {
      await queryClient.invalidateQueries({ queryKey: ["emulators-catalog"] });
      setEditingSlug(null);
    } catch (err) {
      showToast(err instanceof ApiError ? err.detail : "Save failed.", "error");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(entry: CatalogEntry) {
    if (
      !window.confirm(
        `Remove "${entry.name}"? This unregisters the binary but does not delete files.`,
      )
    )
      return;
    try {
      const { token } = await apiFetch<{ token: string }>(
        `/api/v1/emulator-items/${entry.slug}/confirm-token`,
      );
      await apiFetch(`/api/v1/emulator-items/${entry.slug}`, {
        method: "DELETE",
        body: JSON.stringify({ confirmation_token: token }),
      });
      await queryClient.invalidateQueries({ queryKey: ["emulators-catalog"] });
    } catch (err) {
      showToast(err instanceof ApiError ? err.detail : "Remove failed.", "error");
    }
  }

  async function handleAutoDetect() {
    await queryClient.invalidateQueries({ queryKey: ["emulators-catalog"] });
  }

  return (
    <div className="flex flex-col min-h-full">
      <TopBar>
        <span style={{ flex: 1 }} />
        <button
          type="button"
          onClick={handleAutoDetect}
          className="ml-2 rounded-lg px-3.5 py-2 text-sm font-semibold transition-colors duration-[120ms]"
          style={{
            fontFamily: "var(--font-display)",
            background: "rgb(var(--surface-2))",
            border: "1px solid rgb(var(--border))",
            color: "rgb(var(--fg-1))",
            cursor: "pointer",
          }}
        >
          Auto-detect
        </button>
      </TopBar>

      <div className="p-6">
        <div className="mb-3 flex items-baseline gap-2.5">
          <h2
            style={{
              fontFamily: "var(--font-display)",
              fontWeight: 600,
              fontSize: '1.125rem',
              letterSpacing: "-0.01em",
              margin: 0,
              color: "rgb(var(--fg-1))",
            }}
          >
            Installed backends
          </h2>
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: '0.8125rem',
              color: "rgb(var(--fg-3))",
            }}
          >
            {installedCount} of {emulatorEntries.length} ready
          </span>
        </div>

        {isLoading ? (
          <div
            style={{
              color: "rgb(var(--fg-3))",
              fontFamily: "var(--font-display)",
              fontSize: '0.875rem',
            }}
          >
            Loading…
          </div>
        ) : emulatorEntries.length === 0 ? (
          <div
            className="rounded-xl p-10 text-center text-sm"
            style={{
              border: "1px dashed rgb(var(--border-strong))",
              color: "rgb(var(--fg-3))",
              backgroundImage:
                "repeating-linear-gradient(0deg, transparent 0 11px, rgb(var(--peach-500) / 0.04) 11px 12px), repeating-linear-gradient(90deg, transparent 0 11px, rgb(var(--peach-500) / 0.04) 11px 12px)",
            }}
          >
            No emulators found. Check your configuration.
          </div>
        ) : (
          <div
            className="grid gap-3.5"
            style={{ gridTemplateColumns: "1fr 1fr" }}
          >
            {emulatorEntries.map((entry) => (
              <EmulatorCard
                key={entry.slug}
                entry={entry}
                onClick={() => navigate(`/emulators/${entry.slug}`)}
                editing={editingSlug === entry.slug}
                editPath={editPath}
                onEditPathChange={setEditPath}
                onEdit={() => handleStartEdit(entry)}
                onSave={() => handleSavePath(entry.slug)}
                onCancelEdit={() => setEditingSlug(null)}
                onDelete={() => handleDelete(entry)}
                saving={saving && editingSlug === entry.slug}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
