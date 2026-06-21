import { Button, FormField, Input, Modal } from "@/ui";
import { cn } from "@/lib/utils";
import { RATING_OPTIONS as BASE_RATING_OPTIONS } from "@/generated/constants";

export interface AddUserForm {
  name: string;
  pin: string;
  can_launch_media: boolean;
  can_edit_library: boolean;
  can_edit_platforms: boolean;
  can_manage_profiles: boolean;
  can_edit_settings: boolean;
  is_admin: boolean;
  max_content_rating: string;
  block_unrated_media: boolean;
  session_token_ttl: string;
}

const PERMISSION_FLAGS: { key: keyof AddUserForm; label: string }[] = [
  { key: "can_launch_media", label: "Launch media" },
  { key: "can_edit_library", label: "Edit library" },
  { key: "can_edit_platforms", label: "Edit platforms" },
  { key: "can_manage_profiles", label: "Manage profiles" },
  { key: "can_edit_settings", label: "Edit settings" },
  { key: "is_admin", label: "Admin" },
];

const RATING_OPTIONS = [
  { value: "", label: "No restriction" },
  ...BASE_RATING_OPTIONS.slice(1),
];

const SELECT_CLASS =
  "w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-[#ff8a5c] focus:outline-none dark:border-neutral-700 dark:bg-surface-800 dark:text-neutral-100";

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
        "relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-[#ff8a5c] focus:ring-offset-2",
        checked ? "bg-[#ff8a5c]" : "bg-neutral-300 dark:bg-neutral-600",
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

interface AddAccountModalProps {
  open: boolean;
  form: AddUserForm;
  errors: Partial<Record<keyof AddUserForm, string>>;
  submitting: boolean;
  error: string | null;
  isOwner: boolean;
  setField: <K extends keyof AddUserForm>(key: K, value: AddUserForm[K]) => void;
  onSubmit: () => void;
  onClose: () => void;
}

export function AddAccountModal({
  open,
  form,
  errors,
  submitting,
  error,
  isOwner,
  setField,
  onSubmit,
  onClose,
}: AddAccountModalProps) {
  return (
    <Modal
      open={open}
      title="Add Account"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={onSubmit} loading={submitting}>
            Create Account
          </Button>
        </>
      }
    >
      <FormField label="Name" htmlFor="add-name" required error={errors.name}>
        <Input
          id="add-name"
          value={form.name}
          onChange={(e) => setField("name", e.target.value)}
          placeholder="Alex"
          hasError={!!errors.name}
        />
      </FormField>

      <FormField
        label="PIN"
        htmlFor="add-pin"
        hint="4–6 digits. Leave blank for no PIN."
        error={errors.pin}
      >
        <Input
          id="add-pin"
          type="password"
          inputMode="numeric"
          maxLength={6}
          value={form.pin}
          onChange={(e) => setField("pin", e.target.value.replace(/\D/g, ""))}
          placeholder="••••"
          hasError={!!errors.pin}
        />
      </FormField>

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
                  setField(key as keyof AddUserForm, e.target.checked as never)
                }
                className="h-4 w-4 rounded border-neutral-300 text-[#ff8a5c] focus:ring-[#ff8a5c] dark:border-neutral-600"
              />
              {label}
            </label>
          ))}
        </div>
      </fieldset>

      <FormField label="Max Content Rating" htmlFor="add-rating">
        <select
          id="add-rating"
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

      <FormField label="Block unrated media" htmlFor="add-block-unrated">
        <div className="mt-1 flex items-center gap-3">
          <Toggle
            id="add-block-unrated"
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
          htmlFor="add-session-expiry"
          hint="Leave blank for no timeout."
        >
          <Input
            id="add-session-expiry"
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

      {error && (
        <p role="alert" className="text-sm text-red-500 dark:text-red-400">
          ❌ {error}
        </p>
      )}
    </Modal>
  );
}
