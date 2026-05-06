import { useState, useCallback } from 'react'

export interface ConfirmOptions {
  title: string
  consequence: string
  destructive?: boolean
}

interface ConfirmState {
  open: boolean
  options: ConfirmOptions | null
  resolve: ((confirmed: boolean) => void) | null
}

export function useConfirm() {
  const [state, setState] = useState<ConfirmState>({
    open: false,
    options: null,
    resolve: null,
  })

  const confirm = useCallback((options: ConfirmOptions): Promise<boolean> => {
    return new Promise((resolve) => {
      setState({ open: true, options, resolve })
    })
  }, [])

  const handleConfirm = useCallback(() => {
    state.resolve?.(true)
    setState({ open: false, options: null, resolve: null })
  }, [state.resolve])

  const handleCancel = useCallback(() => {
    state.resolve?.(false)
    setState({ open: false, options: null, resolve: null })
  }, [state.resolve])

  return {
    confirm,
    isOpen: state.open,
    options: state.options,
    handleConfirm,
    handleCancel,
  }
}
