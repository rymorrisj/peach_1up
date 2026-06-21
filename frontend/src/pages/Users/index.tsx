import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import TopBar from "@/components/layout/TopBar";
import { apiFetch, ApiError } from "@/api/client";
import { useAppContext } from "@/context/useAppContext";
import { Button } from "@/ui";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import UserSwitcher from "@/components/UserSwitcher";
import { UserList } from "./components/UserList";
import { AddAccountModal, type AddUserForm } from "./components/AddAccountModal";
import { ResetPinModal, type ResetPinTarget } from "./components/ResetPinModal";
import type { components } from "@shared/types";

type User = components["schemas"]["UserRead"];

const EMPTY_ADD_FORM: AddUserForm = {
  name: "",
  pin: "",
  can_launch_media: true,
  can_edit_library: false,
  can_edit_platforms: false,
  can_manage_profiles: false,
  can_edit_settings: false,
  is_admin: false,
  max_content_rating: "",
  block_unrated_media: false,
  session_token_ttl: "",
};

type ActionState = {
  userId: number;
  action: "unlock" | "delete";
  submitting: boolean;
} | null;

export default function Users() {
  const { state: appState } = useAppContext();
  const queryClient = useQueryClient();
  const isAdmin = appState.activeUser?.is_admin ?? false;

  const { data: users, isLoading: usersLoading } = useQuery<User[]>({
    queryKey: ["users"],
    queryFn: () => apiFetch<User[]>("/api/v1/users"),
  });

  const [addOpen, setAddOpen] = useState(false);
  const [addForm, setAddForm] = useState<AddUserForm>(EMPTY_ADD_FORM);
  const [addErrors, setAddErrors] = useState<
    Partial<Record<keyof AddUserForm, string>>
  >({});
  const [addSubmitting, setAddSubmitting] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const [resetPinTarget, setResetPinTarget] = useState<ResetPinTarget | null>(
    null,
  );
  const [actionState, setActionState] = useState<ActionState>(null);

  function setAddField<K extends keyof AddUserForm>(
    key: K,
    value: AddUserForm[K],
  ) {
    setAddForm((prev) => ({ ...prev, [key]: value }));
    setAddErrors((prev) => ({ ...prev, [key]: undefined }));
  }

  function validateAdd(): boolean {
    const errors: Partial<Record<keyof AddUserForm, string>> = {};
    if (!addForm.name.trim()) errors.name = "Name is required.";
    if (addForm.pin && !/^\d{4,6}$/.test(addForm.pin))
      errors.pin = "PIN must be 4–6 digits.";
    setAddErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function handleAddUser() {
    if (!validateAdd()) return;
    setAddSubmitting(true);
    setAddError(null);
    try {
      await apiFetch("/api/v1/users", {
        method: "POST",
        body: JSON.stringify({
          name: addForm.name.trim(),
          pin: addForm.pin || undefined,
          can_launch_media: addForm.can_launch_media,
          can_edit_library: addForm.can_edit_library,
          can_edit_platforms: addForm.can_edit_platforms,
          can_manage_profiles: addForm.can_manage_profiles,
          can_edit_settings: addForm.can_edit_settings,
          is_admin: addForm.is_admin,
          max_content_rating: addForm.max_content_rating || null,
          block_unrated_media: addForm.block_unrated_media,
          session_token_ttl: addForm.session_token_ttl
            ? parseInt(addForm.session_token_ttl, 10)
            : null,
        }),
      });
      setAddOpen(false);
      setAddForm(EMPTY_ADD_FORM);
      await queryClient.invalidateQueries({ queryKey: ["users"] });
    } catch (err) {
      setAddError(
        err instanceof ApiError ? err.detail : "Failed to create user.",
      );
    } finally {
      setAddSubmitting(false);
    }
  }

  async function handleResetPin() {
    if (!resetPinTarget || resetPinTarget.submitting) return;
    if (!/^\d{4,6}$/.test(resetPinTarget.pin)) {
      setResetPinTarget((p) => p && { ...p, error: "PIN must be 4–6 digits." });
      return;
    }
    setResetPinTarget((p) => p && { ...p, submitting: true, error: null });
    try {
      await apiFetch(`/api/v1/users/${resetPinTarget.user.id}/reset-pin`, {
        method: "POST",
        body: JSON.stringify({ pin: resetPinTarget.pin }),
      });
      await queryClient.invalidateQueries({ queryKey: ["users"] });
      setResetPinTarget(null);
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : "Failed to reset PIN.";
      setResetPinTarget((p) => p && { ...p, submitting: false, error: msg });
    }
  }

  async function handleUnlock(user: User) {
    setActionState({ userId: user.id, action: "unlock", submitting: true });
    try {
      await apiFetch(`/api/v1/users/${user.id}/unlock`, { method: "POST" });
      await queryClient.invalidateQueries({ queryKey: ["users"] });
    } catch {
      // error silently — list will not change
    } finally {
      setActionState(null);
    }
  }

  async function handleDelete(user: User) {
    if (!confirm(`Delete account "${user.name}"? This cannot be undone.`))
      return;
    setActionState({ userId: user.id, action: "delete", submitting: true });
    try {
      await apiFetch(`/api/v1/users/${user.id}`, { method: "DELETE" });
      await queryClient.invalidateQueries({ queryKey: ["users"] });
    } catch {
      // error silently
    } finally {
      setActionState(null);
    }
  }

  return (
    <div className="flex flex-col min-h-full">
      <TopBar title="Users" />
      <div className="p-6">
        <div className="max-w-xl space-y-10">
          <UserSwitcher />

          <section>
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500">
                Users
              </h2>
              {isAdmin && (
                <Button
                  size="sm"
                  onClick={() => {
                    setAddForm(EMPTY_ADD_FORM);
                    setAddError(null);
                    setAddErrors({});
                    setAddOpen(true);
                  }}
                >
                  + Add Account
                </Button>
              )}
            </div>

            {usersLoading ? (
              <div className="mt-4 flex items-center gap-2 text-sm text-neutral-500">
                <LoadingSpinner label="Loading users…" />
                <span aria-hidden="true">Loading users…</span>
              </div>
            ) : (
              <UserList
                users={users ?? []}
                isAdmin={isAdmin}
                actionState={actionState}
                onResetPin={(user) =>
                  setResetPinTarget({
                    user,
                    pin: "",
                    error: null,
                    submitting: false,
                  })
                }
                onUnlock={handleUnlock}
                onDelete={handleDelete}
              />
            )}
          </section>
        </div>

        <AddAccountModal
          open={addOpen}
          form={addForm}
          errors={addErrors}
          submitting={addSubmitting}
          error={addError}
          isOwner={!!appState.activeUser?.is_owner}
          setField={setAddField}
          onSubmit={handleAddUser}
          onClose={() => setAddOpen(false)}
        />

        {resetPinTarget && (
          <ResetPinModal
            target={resetPinTarget}
            onChangePin={(pin) =>
              setResetPinTarget((p) => p && { ...p, pin, error: null })
            }
            onSubmit={handleResetPin}
            onClose={() => setResetPinTarget(null)}
          />
        )}
      </div>
    </div>
  );
}
