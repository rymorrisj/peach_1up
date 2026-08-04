// Three-way sentinel for the launch_commands PATCH field. undefined means
// not yet loaded (only true before the collection query resolves, never
// once a caller can actually save) and falls back to whatever is already
// stored. null means never configured or preserve, and is sent verbatim so
// the backend's exclude_none treats it as "field omitted", leaving the
// stored value untouched. [] means explicitly cleared, and is sent verbatim,
// persisting as an empty list (no auto-run). An incidental save (editing an
// unrelated field, never touching the commands UI) must resend whichever of
// null or [] is already current, not silently convert one into the other.
export function resolveLaunchCommands(
  launchCommands: string[] | null | undefined,
  storedLaunchCommands: string[] | null | undefined,
): string[] | null {
  return launchCommands === undefined ? (storedLaunchCommands ?? null) : launchCommands;
}
