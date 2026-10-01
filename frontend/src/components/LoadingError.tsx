// frontend/src/components/LoadingError.tsx

export function LoadingState({ label = "Loading..." }: { label?: string }) {
  return <div className="p-6 text-center text-gray-500">{label}</div>;
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
      Couldn't load this: {message}
    </div>
  );
}
