import { useState } from "react";
import { apiFetch, ApiError } from "@/api/client";
import { useAppContext } from "@/context/useAppContext";
import type { components } from "@shared/types";
type UserRead = components["schemas"]["UserItemRead"];

interface Step0OwnerProps {
  onNext: () => void;
}

export default function Step0Owner({ onNext }: Step0OwnerProps) {
  const { dispatch } = useAppContext();
  const [name, setName] = useState("");
  const [pin, setPin] = useState("");
  const [confirmPin, setConfirmPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (!name.trim()) {
      setError("Name is required.");
      return;
    }
    if (!/^\d{4,6}$/.test(pin)) {
      setError("PIN must be 4–6 digits.");
      return;
    }
    if (pin !== confirmPin) {
      setError("PINs do not match.");
      return;
    }

    setSaving(true);
    try {
      const resp = await apiFetch<{ user: UserRead }>("/api/v1/auth/setup-owner", {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          pin,
          confirm_pin: confirmPin,
        }),
      });
      dispatch({ type: "SET_ACTIVE_USER", payload: resp.user });
      onNext();
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.detail
          : "Failed to create owner account.";
      setError(message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section>
      <h2 className="mb-2 text-2xl font-semibold text-neutral-900 dark:text-neutral-100">
        Create Owner Account
      </h2>
      <p className="mb-6 text-sm text-neutral-500 dark:text-neutral-400">
        Set up the owner account for this Peach 1UP installation. The PIN
        protects access and cannot be recovered if lost — store it somewhere
        safe.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label
            htmlFor="owner-name"
            className="mb-1 block text-sm font-medium text-neutral-700 dark:text-neutral-300"
          >
            Name
          </label>
          <input
            id="owner-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your name"
            autoComplete="name"
            className="w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 placeholder:text-neutral-400 focus:border-[#ff8a5c] focus:outline-none dark:border-neutral-700 dark:bg-surface-800 dark:text-neutral-100 dark:placeholder:text-neutral-600"
          />
        </div>

        <div>
          <label
            htmlFor="owner-pin"
            className="mb-1 block text-sm font-medium text-neutral-700 dark:text-neutral-300"
          >
            PIN (4–6 digits)
          </label>
          <input
            id="owner-pin"
            type="password"
            inputMode="numeric"
            value={pin}
            onChange={(e) =>
              setPin(e.target.value.replace(/\D/g, "").slice(0, 6))
            }
            placeholder="••••"
            autoComplete="new-password"
            className="w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 placeholder:text-neutral-400 focus:border-[#ff8a5c] focus:outline-none dark:border-neutral-700 dark:bg-surface-800 dark:text-neutral-100 dark:placeholder:text-neutral-600"
          />
        </div>

        <div>
          <label
            htmlFor="owner-confirm-pin"
            className="mb-1 block text-sm font-medium text-neutral-700 dark:text-neutral-300"
          >
            Confirm PIN
          </label>
          <input
            id="owner-confirm-pin"
            type="password"
            inputMode="numeric"
            value={confirmPin}
            onChange={(e) =>
              setConfirmPin(e.target.value.replace(/\D/g, "").slice(0, 6))
            }
            placeholder="••••"
            autoComplete="new-password"
            className="w-full rounded-md border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 placeholder:text-neutral-400 focus:border-[#ff8a5c] focus:outline-none dark:border-neutral-700 dark:bg-surface-800 dark:text-neutral-100 dark:placeholder:text-neutral-600"
          />
        </div>

        {error && (
          <p role="alert" className="text-xs text-[#ff6a55]">
            {error}
          </p>
        )}

        <div className="flex justify-end pt-2">
          <button
            type="submit"
            disabled={saving}
            className="rounded-md bg-[#ff8a5c] px-6 py-2.5 text-sm font-medium text-white hover:opacity-90 disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#ff8a5c]"
          >
            {saving ? "Creating…" : "Create Account"}
          </button>
        </div>
      </form>
    </section>
  );
}
