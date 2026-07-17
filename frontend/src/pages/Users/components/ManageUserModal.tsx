import { Button, FormField, Input, Modal } from "@/ui";
import { cn } from "@/lib/utils";
import { RATING_OPTIONS as BASE_RATING_OPTIONS } from "@/generated/constants";

export type ManageUserMode = "create" | "edit";

export interface ManageUserForm {
  name: string;
  pin: string;
  can_launch_media: boolean;
  can_manage_game: boolean;
  can_manage_environment: boolean;
  can_manage_media: boolean;
  can_manage_controllerMapping: boolean;
  can_manage_settings: boolean;
  can_manage_users: boolean;
  is_admin: boolean;
  max_content_rating: string;
  block_unrated_media: boolean;
  session_token_ttl: string;
}

const PERMISSION_FLAGS: { key: keyof ManageUserForm; label: string }[] = [
  { key: "can_launch_media", label: "Launch media" },
  { key: "can_manage_game", label: "Edit software" },
  { key: "can_manage_environment", label: "Edit environments" },
  { key: "can_manage_media", label: "Edit media" },
  { key: "can_manage_controllerMapping", label: "Manage controllers" },
  { key: "can_manage_settings", label: "Edit settings" },
  { key: "can_manage_users", label: "Manage own account" },
  { key: "is_admin", label: "Admin" },
];

const RATING_OPTIONS = [
  { value: "", label: "No restriction" },
  ...BASE_RATING_OPTIONS.slice(1),
];

const SELECT_CLASS =
  "w-full rounded-md border border-neutral-300 bg-surface-2 px-3 py-2 text-sm text-neutral-900 focus:border-accent focus:outline-none dark:border-neutral-700 dark:text-neutral-100";

function Toggle({
  checked,
  onChange,
  id,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  id: string;
}) {
  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2",
        checked ? "bg-accent" : "bg-neutral-300 dark:bg-neutral-600",
      )}
    >
      <span
        className={cn(
          "inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform",
          checked ? "translate-x-[1.125rem]" : "translate-x-[0.1875rem]",
        )}
      />
    </button>
  );
}

interface ManageUserModalProps {
  mode: ManageUserMode;
  open: boolean;
  targetName?: string;
  form: ManageUserForm;
  errors: Partial<Record<keyof ManageUserForm, string>>;
  submitting: boolean;
  error: string | null;
  isOwner: boolean;
  canEditAdminFields: boolean;
  setField: <K extends keyof ManageUserForm>(key: K, value: ManageUserForm[K]) => void;
  onSubmit: () => void;
  onClose: () => void;
}

export function ManageUserModal({
  mode,
  open,
  targetName,
  form,
  errors,
  submitting,
  error,
  isOwner,
  canEditAdminFields,
  setField,
  onSubmit,
  onClose,
}: ManageUserModalProps) {
  const isCreate = mode === "create";

  return (
    <Modal
      open={open}
      title={isCreate ? "Add Account" : `Edit ${targetName ?? "Account"}`}
      onClose={onClose}
      busy={submitting}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={onSubmit} loading={submitting}>
            {isCreate ? "Create Account" : "Save Changes"}
          </Button>
        </>
      }
    >
      <FormField label="Name" htmlFor="manage-name" required error={errors.name}>
        <Input
          id="manage-name"
          value={form.name}
          onChange={(e) => setField("name", e.target.value)}
          placeholder="Alex"
          hasError={!!errors.name}
        />
      </FormField>

      <FormField
        label={isCreate ? "PIN" : "New PIN"}
        htmlFor="manage-pin"
        hint={isCreate ? "4–6 digits. Leave blank for no PIN." : "4–6 digits. Leave blank to keep current PIN."}
        error={errors.pin}
      >
        <Input
          id="manage-pin"
          type="password"
          inputMode="numeric"
          maxLength={6}
          value={form.pin}
          onChange={(e) => setField("pin", e.target.value.replace(/\D/g, ""))}
          placeholder="••••"
          hasError={!!errors.pin}
        />
      </FormField>

      {canEditAdminFields && (
        <>
          <fieldset>
            <legend className="mb-2 text-sm font-medium text-neutral-700 dark:text-neutral-300">
              Permissions
            </legend>
            <div className="grid grid-cols-2 gap-x-4 gap-y-2">
              {PERMISSION_FLAGS.map(({ key, label }) => (
                <label
                  key={key}
                  className="flex items-center gap-2 text-sm text-neutral-700 dark:text-neutral-300"
                >
                  <input
                    type="checkbox"
                    checked={form[key] as boolean}
                    onChange={(e) =>
                      setField(key as keyof ManageUserForm, e.target.checked as never)
                    }
                    className="h-4 w-4 rounded border-neutral-300 text-accent focus:ring-accent dark:border-neutral-600"
                  />
                  {label}
                </label>
              ))}
            </div>
          </fieldset>

          <FormField label="Max Content Rating" htmlFor="manage-rating">
            <select
              id="manage-rating"
              value={form.max_content_rating}
              onChange={(e) => setField("max_content_rating", e.target.value)}
              className={SELECT_CLASS}
            >
              {RATING_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </FormField>

          <FormField label="Block unrated media" htmlFor="manage-block-unrated">
            <div className="mt-1 flex items-center gap-3">
              <Toggle
                id="manage-block-unrated"
                checked={form.block_unrated_media}
                onChange={(v) => setField("block_unrated_media", v)}
              />
              <span className="text-sm text-neutral-600 dark:text-neutral-300">
                {form.block_unrated_media
                  ? "Yes — hide items with no rating"
                  : "No"}
              </span>
            </div>
          </FormField>

          {isOwner && (
            <FormField
              label="Session timeout (minutes)"
              htmlFor="manage-session-expiry"
              hint="Leave blank for no timeout."
            >
              <Input
                id="manage-session-expiry"
                type="number"
                min={1}
                value={form.session_token_ttl}
                onChange={(e) =>
                  setField("session_token_ttl", e.target.value.replace(/\D/g, ""))
                }
                placeholder="e.g. 60"
              />
            </FormField>
          )}
        </>
      )}

      {error && (
        <p role="alert" className="text-sm text-red-500 dark:text-red-400">
          ❌ {error}
        </p>
      )}
    </Modal>
  );
}
