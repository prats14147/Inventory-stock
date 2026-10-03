// frontend/src/components/LoadingError.tsx
//
// Shared loading/error states so every page fails the same way: skeleton
// rows while fetching, one error card with a retry button on failure.

export function LoadingState({ label = "Loading..." }: { label?: string }) {
  return (
    <div className="space-y-2" role="status" aria-label={label}>
      <p className="text-sm text-gray-500">{label}</p>
      <div className="animate-pulse space-y-2">
        <div className="h-10 rounded-lg bg-gray-200/70" />
        <div className="h-10 rounded-lg bg-gray-200/70" />
        <div className="h-10 rounded-lg bg-gray-200/50" />
      </div>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
      <p className="font-medium">Couldn't load this data.</p>
      <p className="mt-1">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded-md border border-red-300 bg-white px-3 py-1 text-xs font-medium text-red-700 hover:bg-red-100"
        >
          Try again
        </button>
      )}
    </div>
  );
}
