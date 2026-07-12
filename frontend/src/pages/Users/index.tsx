import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import TopBar from "@/components/layout/TopBar";
import { apiFetch, ApiError } from "@/api/client";
import { useAppContext } from "@/context/useAppContext";
import { Button } from "@/ui";
import LoadingSpinner from "@/components/common/LoadingSpinner";
import UserSwitcher from "@/components/UserSwitcher";
import { UserList } from "./components/UserList";
import {
  ManageUserModal,
  type ManageUserForm,
  type ManageUserMode,
} from "./components/ManageUserModal";
import { ResetPinModal, type ResetPinTarget } from "./components/ResetPinModal";
import type { components } from "@shared/types";

type User = components["schemas"]["UserRead"];

const EMPTY_MANAGE_USER_FORM: ManageUserForm = {
  name: "",
  pin: "",
  can_launch_media: true,
  can_manage_game: false,
  can_manage_environment: false,
  can_manage_media: false,
  can_manage_controllerMapping: false,
  can_manage_settings: false,
  can_manage_users: false,
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
  const isOwner = appState.activeUser?.is_owner ?? false;
  const activeUserId = appState.activeUser?.id;

  const { data: users, isLoading: usersLoading } = useQuery<User[]>({
    queryKey: ["users"],
    queryFn: () => apiFetch<User[]>("/api/v1/users"),
  });

  const [manageOpen, setManageOpen] = useState(false);
  const [manageMode, setManageMode] = useState<ManageUserMode>("create");
  const [manageTargetId, setManageTargetId] = useState<number | null>(null);
  const [manageTargetName, setManageTargetName] = useState<string>("");
  const [manageCanEditAdminFields, setManageCanEditAdminFields] = useState(true);
  const [manageForm, setManageForm] = useState<ManageUserForm>(EMPTY_MANAGE_USER_FORM);
  const [manageErrors, setManageErrors] = useState<
    Partial<Record<keyof ManageUserForm, string>>
  >({});
  const [manageSubmitting, setManageSubmitting] = useState(false);
  const [manageError, setManageError] = useState<string | null>(null);

  const [resetPinTarget, setResetPinTarget] = useState<ResetPinTarget | null>(
    null,
  );
  const [actionState, setActionState] = useState<ActionState>(null);

  function setManageField<K extends keyof ManageUserForm>(
    key: K,
    value: ManageUserForm[K],
  ) {
    setManageForm((prev) => ({ ...prev, [key]: value }));
    setManageErrors((prev) => ({ ...prev, [key]: undefined }));
  }

  function openAddUser() {
    setManageMode("create");
    setManageTargetId(null);
    setManageTargetName("");
    setManageCanEditAdminFields(true);
    setManageForm(EMPTY_MANAGE_USER_FORM);
    setManageErrors({});
    setManageError(null);
    setManageOpen(true);
  }

  function openEditUser(user: User) {
    setManageMode("edit");
    setManageTargetId(user.id);
    setManageTargetName(user.name);
    setManageCanEditAdminFields(isOwner || isAdmin);
    setManageForm({
      name: user.name,
      pin: "",
      can_launch_media: user.can_launch_media,
      can_manage_game: user.can_manage_game,
      can_manage_environment: user.can_manage_environment,
      can_manage_media: user.can_manage_media,
      can_manage_controllerMapping: user.can_manage_controllerMapping,
      can_manage_settings: user.can_manage_settings,
      can_manage_users: user.can_manage_users,
      is_admin: user.is_admin,
      max_content_rating: user.max_content_rating ?? "",
      block_unrated_media: user.block_unrated_media,
      session_token_ttl:
        user.session_token_ttl != null ? String(user.session_token_ttl) : "",
    });
    setManageErrors({});
    setManageError(null);
    setManageOpen(true);
  }

  function validateManage(): boolean {
    const errors: Partial<Record<keyof ManageUserForm, string>> = {};
    if (!manageForm.name.trim()) errors.name = "Name is required.";
    if (manageForm.pin && !/^\d{4,6}$/.test(manageForm.pin))
      errors.pin = "PIN must be 4–6 digits.";
    setManageErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function handleManageSubmit() {
    if (!validateManage()) return;
    setManageSubmitting(true);
    setManageError(null);
    try {
      if (manageMode === "create") {
        await apiFetch("/api/v1/users", {
          method: "POST",
          body: JSON.stringify({
            name: manageForm.name.trim(),
            pin: manageForm.pin || undefined,
            can_launch_media: manageForm.can_launch_media,
            can_manage_game: manageForm.can_manage_game,
            can_manage_environment: manageForm.can_manage_environment,
            can_manage_media: manageForm.can_manage_media,
            can_manage_controllerMapping: manageForm.can_manage_controllerMapping,
            can_manage_settings: manageForm.can_manage_settings,
            can_manage_users: manageForm.can_manage_users,
            is_admin: manageForm.is_admin,
            max_content_rating: manageForm.max_content_rating || null,
            block_unrated_media: manageForm.block_unrated_media,
            session_token_ttl: manageForm.session_token_ttl
              ? parseInt(manageForm.session_token_ttl, 10)
              : null,
          }),
        });
      } else if (manageTargetId != null) {
        const patchBody: Record<string, unknown> = {
          name: manageForm.name.trim(),
        };
        if (manageCanEditAdminFields) {
          patchBody.can_launch_media = manageForm.can_launch_media;
          patchBody.can_manage_game = manageForm.can_manage_game;
          patchBody.can_manage_environment = manageForm.can_manage_environment;
          patchBody.can_manage_media = manageForm.can_manage_media;
          patchBody.can_manage_controllerMapping = manageForm.can_manage_controllerMapping;
          patchBody.can_manage_settings = manageForm.can_manage_settings;
          patchBody.can_manage_users = manageForm.can_manage_users;
          patchBody.is_admin = manageForm.is_admin;
          patchBody.max_content_rating = manageForm.max_content_rating || null;
          patchBody.block_unrated_media = manageForm.block_unrated_media;
          if (isOwner) {
            patchBody.session_token_ttl = manageForm.session_token_ttl
              ? parseInt(manageForm.session_token_ttl, 10)
              : null;
          }
        }
        await apiFetch(`/api/v1/users/${manageTargetId}`, {
          method: "PATCH",
          body: JSON.stringify(patchBody),
        });
        if (manageForm.pin) {
          await apiFetch(`/api/v1/users/${manageTargetId}/reset-pin`, {
            method: "POST",
            body: JSON.stringify({ pin: manageForm.pin }),
          });
        }
      }
      setManageOpen(false);
      setManageForm(EMPTY_MANAGE_USER_FORM);
      await queryClient.invalidateQueries({ queryKey: ["users"] });
    } catch (err) {
      setManageError(
        err instanceof ApiError
          ? err.detail
          : manageMode === "create"
            ? "Failed to create user."
            : "Failed to update user.",
      );
    } finally {
      setManageSubmitting(false);
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
              {isOwner && (
                <Button size="sm" onClick={openAddUser}>
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
                activeUserId={activeUserId}
                isAdmin={isAdmin}
                isOwner={isOwner}
                actionState={actionState}
                onEdit={openEditUser}
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

        <ManageUserModal
          mode={manageMode}
          open={manageOpen}
          targetName={manageTargetName}
          form={manageForm}
          errors={manageErrors}
          submitting={manageSubmitting}
          error={manageError}
          isOwner={isOwner}
          canEditAdminFields={manageCanEditAdminFields}
          setField={setManageField}
          onSubmit={handleManageSubmit}
          onClose={() => setManageOpen(false)}
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
