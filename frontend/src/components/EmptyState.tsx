// frontend/src/components/EmptyState.tsx
//
// Shared empty-table/empty-list message with an optional action.
// Gives every page the same "nothing here, do this next" voice instead of
// a bare "No matching rows." line.

import type { ReactNode } from "react";

interface EmptyStateProps {
  title?: string;
  hint?: string;
  action?: ReactNode;
}

export default function EmptyState({ title = "Nothing to show.", hint, action }: EmptyStateProps) {
  return (
    <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 px-4 py-8 text-center">
      <p className="text-sm font-medium text-gray-700">{title}</p>
      {hint && <p className="mx-auto mt-1 max-w-md text-xs text-gray-500">{hint}</p>}
      {action && <div className="mt-3 flex justify-center">{action}</div>}
    </div>
  );
}
