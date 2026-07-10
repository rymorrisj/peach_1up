import { Lock, Unlock, Trash2, KeyRound, Pencil } from "lucide-react";
import { Button } from "@/ui";
import type { components } from "@shared/types";

type User = components["schemas"]["UserRead"];

type ActionState = {
  userId: number;
  action: "unlock" | "delete";
  submitting: boolean;
} | null;

function permissionSummary(user: User): string {
  const labels: string[] = [];
  if (user.can_launch_media) labels.push("launch");
  if (user.can_edit_software) labels.push("software");
  if (user.can_edit_environments) labels.push("environments");
  if (user.can_edit_media) labels.push("media");
  if (user.can_manage_controllers) labels.push("controllers");
  if (user.can_manage_profiles) labels.push("profiles");
  if (user.can_edit_settings) labels.push("settings");
  if (user.can_manage_users) labels.push("self-manage");
  if (user.is_admin) labels.push("admin");
  return labels.length ? labels.join(", ") : "no permissions";
}

interface UserListProps {
  users: User[];
  activeUserId: number | undefined;
  isAdmin: boolean;
  isOwner: boolean;
  actionState: ActionState;
  onEdit: (user: User) => void;
  onResetPin: (user: User) => void;
  onUnlock: (user: User) => void;
  onDelete: (user: User) => void;
}

export function UserList({
  users,
  activeUserId,
  isAdmin,
  isOwner,
  actionState,
  onEdit,
  onResetPin,
  onUnlock,
  onDelete,
}: UserListProps) {
  return (
    <ul
      role="list"
      className="mt-4 divide-y divide-neutral-200 dark:divide-neutral-800"
    >
      {users.map((user) => {
        const isBusy =
          actionState?.userId === user.id && actionState.submitting;
        const canManage =
          !user.is_owner &&
          (isAdmin ||
            isOwner ||
            (user.id === activeUserId && user.can_manage_users));
        return (
          <li key={user.id} className="py-3">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-neutral-900 dark:text-neutral-100">
                    {user.name}
                  </span>
                  {user.is_owner && (
                    <span className="rounded-full bg-peach/15 px-2 py-0.5 text-xs font-medium text-peach">
                      owner
                    </span>
                  )}
                  {user.is_locked && (
                    <span className="flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-600 dark:bg-red-900/30 dark:text-red-400">
                      <Lock size={10} />
                      locked
                    </span>
                  )}
                </div>
                <p className="mt-0.5 truncate text-xs text-neutral-400 dark:text-neutral-500">
                  {permissionSummary(user)}
                  {user.max_content_rating &&
                    ` · max ${user.max_content_rating}`}
                  {user.block_unrated_media && " · block unrated"}
                </p>
              </div>

              {canManage && (
                <div className="flex shrink-0 items-center gap-1.5">
                  <Button
                    variant="ghost"
                    size="sm"
                    title="Edit account"
                    disabled={isBusy}
                    onClick={() => onEdit(user)}
                  >
                    <Pencil size={14} />
                  </Button>
                  {isAdmin && !user.is_owner && (
                    <Button
                      variant="ghost"
                      size="sm"
                      title="Reset PIN"
                      disabled={isBusy}
                      onClick={() => onResetPin(user)}
                    >
                      <KeyRound size={14} />
                    </Button>
                  )}
                  {isAdmin && !user.is_owner && user.is_locked && (
                    <Button
                      variant="ghost"
                      size="sm"
                      title="Unlock account"
                      disabled={isBusy}
                      loading={
                        actionState?.userId === user.id &&
                        actionState.action === "unlock" &&
                        actionState.submitting
                      }
                      onClick={() => onUnlock(user)}
                    >
                      <Unlock size={14} />
                    </Button>
                  )}
                  {isOwner && (
                    <Button
                      variant="destructive"
                      size="sm"
                      title="Delete account"
                      disabled={isBusy}
                      onClick={() => onDelete(user)}
                    >
                      <Trash2 size={14} />
                    </Button>
                  )}
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
