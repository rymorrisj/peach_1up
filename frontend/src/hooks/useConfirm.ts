import { useState, useCallback, useRef } from 'react';

export interface ConfirmOptions {
  title: string;
  consequence: string;
  destructive?: boolean;
  /** Renders an extra checkbox inside the dialog, seeded to defaultChecked.
   * Read its final state via the returned getCheckboxValue() after confirm()
   * resolves true — the confirm() promise itself stays a plain boolean so
   * existing callers are unaffected. */
  checkbox?: { label: string; defaultChecked: boolean };
}

interface ConfirmState {
  open: boolean;
  options: ConfirmOptions | null;
  resolve: ((confirmed: boolean) => void) | null;
}

export function useConfirm() {
  const [state, setState] = useState<ConfirmState>({
    open: false,
    options: null,
    resolve: null,
  });
  const checkedRef = useRef(false);

  const confirm = useCallback((options: ConfirmOptions): Promise<boolean> => {
    checkedRef.current = options.checkbox?.defaultChecked ?? false;
    return new Promise((resolve) => {
      setState({ open: true, options, resolve });
    });
  }, []);

  const handleConfirm = useCallback(
    (checked?: boolean) => {
      if (checked !== undefined) checkedRef.current = checked;
      state.resolve?.(true);
      setState({ open: false, options: null, resolve: null });
    },
    [state.resolve],
  );

  const handleCancel = useCallback(() => {
    state.resolve?.(false);
    setState({ open: false, options: null, resolve: null });
  }, [state.resolve]);

  return {
    confirm,
    isOpen: state.open,
    options: state.options,
    handleConfirm,
    handleCancel,
    getCheckboxValue: () => checkedRef.current,
  };
}
