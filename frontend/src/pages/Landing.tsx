const features = [
  { icon: "▦", title: "Inventory control", text: "Manage products, store stock, deliveries, and recorded sales in one place." },
  { icon: "↗", title: "Demand planning", text: "Review point forecasts, stock coverage, and reorder recommendations." },
  { icon: "▥", title: "Store performance", text: "Explore sales history, revenue, margins, and operational trends." },
  { icon: "✳", title: "Inventory assistant", text: "Ask questions about stock and sales using verified project data." },
];

export default function Landing({ onLogin }: { onLogin: () => void }) {
  return (
    <main className="min-h-screen overflow-hidden bg-gray-50 text-gray-900">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_rgba(59,130,246,0.10),_transparent_48%)]" />
      <div className="relative mx-auto max-w-7xl px-5 py-7 sm:px-8">
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600 text-sm font-bold text-white">AI</span>
            <span className="text-lg font-semibold tracking-tight">InventoryAI</span>
          </div>
          <button onClick={onLogin} className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm transition hover:bg-gray-50">Staff sign in</button>
        </header>

        <section className="grid items-center gap-12 py-16 sm:py-24 lg:grid-cols-[1.05fr_0.95fr]">
          <div>
            <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-brand-200 bg-brand-50 px-3 py-1.5 text-xs font-medium text-brand-700">
              <span aria-hidden="true">✓</span> Clear, accountable stock operations
            </div>
            <h1 className="max-w-2xl text-4xl font-semibold leading-tight tracking-tight sm:text-6xl">Know what’s in stock. Decide what to do next.</h1>
            <p className="mt-6 max-w-xl text-base leading-7 text-gray-600 sm:text-lg">InventoryAI brings store inventory, sales, forecasting, and stock-risk insights together so teams can make better day-to-day decisions.</p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <button onClick={onLogin} className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700">Open your workspace <span aria-hidden="true">→</span></button>
              <span className="text-xs text-gray-500">Staff access is managed by your administrator.</span>
            </div>
          </div>

          <div className="rounded-2xl border border-gray-200 bg-white p-4 shadow-lg shadow-gray-200/60 sm:p-6">
            <div className="flex items-center justify-between border-b border-gray-100 pb-4">
              <div><p className="text-sm font-medium text-gray-900">Operations overview</p><p className="mt-1 text-xs text-gray-500">A single view of inventory health</p></div>
              <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">Workspace</span>
            </div>
            <div className="grid grid-cols-2 gap-3 py-5">
              {[{ label: "Stock on hand", value: "Inventory" }, { label: "Sales activity", value: "Sales" }, { label: "Demand outlook", value: "Forecasts" }, { label: "Items to review", value: "Risk" }].map((item) => (
                <div key={item.label} className="rounded-xl border border-gray-200 bg-gray-50 p-4">
                  <p className="text-xs text-gray-500">{item.label}</p><p className="mt-3 text-xl font-semibold text-gray-900">{item.value}</p>
                </div>
              ))}
            </div>
            <div className="rounded-xl border border-brand-100 bg-brand-50/70 p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-brand-700">Designed for practical decisions</p>
              <p className="mt-2 text-sm leading-6 text-gray-600">Review the numbers, understand the assumptions, and confirm inventory changes with the right access level.</p>
            </div>
          </div>
        </section>

        <section className="grid gap-4 border-t border-gray-200 py-10 sm:grid-cols-2 lg:grid-cols-4">
          {features.map(({ icon, title, text }) => (
            <article key={title} className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
              <span className="text-xl text-brand-600" aria-hidden="true">{icon}</span><h2 className="mt-4 text-sm font-semibold text-gray-900">{title}</h2><p className="mt-2 text-sm leading-6 text-gray-600">{text}</p>
            </article>
          ))}
        </section>
        <footer className="border-t border-gray-200 py-5 text-xs text-gray-500">InventoryAI · Inventory decisions supported by transparent operational data.</footer>
      </div>
    </main>
  );
}
