const features = [
  { icon: "▦", title: "Inventory control", text: "Manage products, store stock, deliveries, and recorded sales in one place." },
  { icon: "↗", title: "Demand planning", text: "Review point forecasts, stock coverage, and reorder recommendations." },
  { icon: "▥", title: "Store performance", text: "Explore sales history, revenue, margins, and operational trends." },
  { icon: "✳", title: "Inventory assistant", text: "Ask questions about stock and sales using verified project data." },
];

export default function Landing({ onLogin }: { onLogin: () => void }) {
  return (
    <main className="min-h-screen overflow-hidden bg-slate-950 text-white">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_rgba(37,99,235,0.28),_transparent_45%)]" />
      <div className="relative mx-auto max-w-7xl px-5 py-7 sm:px-8">
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500 text-sm font-bold">IA</span>
            <span className="text-lg font-semibold tracking-tight">InventoryAI</span>
          </div>
          <button onClick={onLogin} className="rounded-lg border border-white/20 px-4 py-2 text-sm font-medium text-white transition hover:bg-white/10">Staff sign in</button>
        </header>

        <section className="grid items-center gap-12 py-16 sm:py-24 lg:grid-cols-[1.05fr_0.95fr]">
          <div>
            <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-blue-300/20 bg-blue-400/10 px-3 py-1.5 text-xs font-medium text-blue-200">
              <span aria-hidden="true">✓</span> Clear, accountable stock operations
            </div>
            <h1 className="max-w-2xl text-4xl font-semibold leading-tight tracking-tight sm:text-6xl">Know what’s in stock. Decide what to do next.</h1>
            <p className="mt-6 max-w-xl text-base leading-7 text-slate-300 sm:text-lg">InventoryAI brings store inventory, sales, forecasting, and stock-risk insights together so teams can make better day-to-day decisions.</p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <button onClick={onLogin} className="inline-flex items-center gap-2 rounded-lg bg-blue-500 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-blue-950/40 transition hover:bg-blue-400">Open your workspace <span aria-hidden="true">→</span></button>
              <span className="text-xs text-slate-400">Staff access is managed by your administrator.</span>
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-white/[0.06] p-4 shadow-2xl shadow-black/30 backdrop-blur sm:p-6">
            <div className="flex items-center justify-between border-b border-white/10 pb-4">
              <div><p className="text-sm font-medium text-white">Operations overview</p><p className="mt-1 text-xs text-slate-400">A single view of inventory health</p></div>
              <span className="rounded-full bg-emerald-400/10 px-2.5 py-1 text-xs font-medium text-emerald-300">Live workspace</span>
            </div>
            <div className="grid grid-cols-2 gap-3 py-5">
              {[{ label: "Stock on hand", value: "Inventory" }, { label: "Sales activity", value: "Sales" }, { label: "Demand outlook", value: "Forecasts" }, { label: "Items to review", value: "Risk" }].map((item) => (
                <div key={item.label} className="rounded-xl border border-white/10 bg-slate-900/70 p-4">
                  <p className="text-xs text-slate-400">{item.label}</p><p className="mt-3 text-xl font-semibold text-white">{item.value}</p>
                </div>
              ))}
            </div>
            <div className="rounded-xl border border-blue-300/15 bg-blue-400/[0.07] p-4">
              <p className="text-xs font-medium uppercase tracking-wide text-blue-200">Designed for practical decisions</p>
              <p className="mt-2 text-sm leading-6 text-slate-300">Review the numbers, understand the assumptions, and confirm inventory changes with the right access level.</p>
            </div>
          </div>
        </section>

        <section className="grid gap-4 border-t border-white/10 py-10 sm:grid-cols-2 lg:grid-cols-4">
          {features.map(({ icon, title, text }) => (
            <article key={title} className="rounded-xl border border-white/10 bg-white/[0.035] p-5">
              <span className="text-xl text-blue-300" aria-hidden="true">{icon}</span><h2 className="mt-4 text-sm font-semibold">{title}</h2><p className="mt-2 text-sm leading-6 text-slate-400">{text}</p>
            </article>
          ))}
        </section>
        <footer className="border-t border-white/10 py-5 text-xs text-slate-500">InventoryAI · Inventory decisions supported by transparent operational data.</footer>
      </div>
    </main>
  );
}
