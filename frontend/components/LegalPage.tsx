export function LegalPage({ title, updated, children }: { title: string; updated?: string; children: React.ReactNode }) {
  return (
    <div className="max-w-3xl mx-auto px-4 py-12">
      <h1 className="text-3xl font-bold text-gray-900 mb-2">{title}</h1>
      {updated && <p className="text-sm text-gray-500 mb-8">Last updated {updated}</p>}
      <div className="space-y-4 text-gray-700 leading-relaxed [&_h2]:text-xl [&_h2]:font-semibold [&_h2]:text-gray-900 [&_h2]:mt-8 [&_ul]:list-disc [&_ul]:pl-6 [&_ul]:space-y-1 [&_a]:text-brand-600 [&_a]:underline">
        {children}
      </div>
    </div>
  )
}
