import { createContext, useContext, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

/**
 * HIG: a window's actions live in its toolbar, not in the content. The window shell owns the
 * toolbar element; each screen places its own items there with <ToolbarItems>, keeping the
 * logic that drives them inside the screen.
 */
export const ToolbarSlot = createContext<HTMLElement | null>(null);

export function ToolbarItems({ children }: { children: ReactNode }) {
  const slot = useContext(ToolbarSlot);
  return slot ? createPortal(children, slot) : null;
}
