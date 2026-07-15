import { useEffect, useState } from 'react'

interface OrderableDisc {
  id: number
  disc_number: number
  executable_path: string | null
}

interface UseDiscOrderOptions {
  discs: OrderableDisc[]
  onLaunchDiscChange?: (executablePath: string) => void
}

// Staged disc order (leaf ids, top-to-bottom) from <DiscOrderList>. Never
// calls the API itself, the page's own save mutation persists it. null means
// no local edit yet, so displayedOrder falls back to the collection's
// current disc_number order.
export function useDiscOrder({ discs, onLaunchDiscChange }: UseDiscOrderOptions) {
  const [discOrder, setDiscOrder] = useState<number[] | null>(null)

  // Reordering discs changes which leaf is the (staged) launch target,
  // resync the caller's Launch File field to that disc's own
  // executable_path so it never shows a stale value from whichever disc
  // used to be on top.
  useEffect(() => {
    if (discOrder == null) return
    const newLaunchDisc = discs.find((d) => d.id === discOrder[0])
    onLaunchDiscChange?.(newLaunchDisc?.executable_path ?? '')
    // Only re-run when the staged top disc actually changes, not on every
    // keystroke elsewhere in the form.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [discOrder?.[0]])

  const sortedIds = [...discs].sort((a, b) => a.disc_number - b.disc_number).map((d) => d.id)
  const displayedOrder = discOrder ?? sortedIds

  function isReorderStaged(currentOrderIds: number[]): boolean {
    return (
      discOrder != null &&
      (discOrder.length !== currentOrderIds.length ||
        discOrder.some((id, i) => id !== currentOrderIds[i]))
    )
  }

  function reset() {
    setDiscOrder(null)
  }

  return { discOrder, setDiscOrder, displayedOrder, isReorderStaged, reset }
}
