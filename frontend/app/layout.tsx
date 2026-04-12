import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'CampFinder -- There is finally a better way to plan your kid\'s summer.',
  description: 'Search verified summer camps near you. Filter by age, type, price, and interests. Request info in one click.',
  openGraph: {
    title: 'CampFinder',
    description: 'There is finally a better way to plan your kid\'s summer.',
    type: 'website',
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-white text-gray-900 antialiased">
        <header className="border-b border-gray-100 bg-white sticky top-0 z-50">
          <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
            <a href="/" className="flex items-center gap-2 font-bold text-xl text-brand-700">
              <span className="text-2xl">⛺</span>
              CampFinder
            </a>
            <nav className="hidden md:flex items-center gap-6 text-sm font-medium text-gray-600">
              <a href="/search" className="hover:text-brand-700 transition-colors">Find Camps</a>
              <a href="/operators" className="hover:text-brand-700 transition-colors">For Camps</a>
              <a href="/operators/claim" className="hover:text-brand-700 transition-colors">Claim Listing</a>
            </nav>
            <a
              href="/operators/submit"
              className="bg-brand-600 text-white text-sm font-semibold px-4 py-2 rounded-lg hover:bg-brand-700 transition-colors"
            >
              List your camp
            </a>
          </div>
        </header>
        <main>{children}</main>
        <footer className="bg-gray-50 border-t border-gray-100 mt-16">
          <div className="max-w-6xl mx-auto px-4 py-10 flex flex-col md:flex-row justify-between gap-6 text-sm text-gray-500">
            <div>
              <p className="font-semibold text-gray-700 mb-1">⛺ CampFinder</p>
              <p className="mb-0.5">There is finally a better way to plan your kid's summer.</p>
              <p className="text-xs text-gray-400">The structured camp discoverability layer for the AI economy.</p>
            </div>
            <div className="flex gap-8">
              <div>
                <p className="font-semibold text-gray-700 mb-2">Parents</p>
                <a href="/search" className="block hover:text-brand-600">Search Camps</a>
              </div>
              <div>
                <p className="font-semibold text-gray-700 mb-2">Camps</p>
                <a href="/operators" className="block hover:text-brand-600">For Camps</a>
                <a href="/operators/submit" className="block hover:text-brand-600">List Your Camp</a>
                <a href="/operators/claim" className="block hover:text-brand-600">Claim Listing</a>
              </div>
            </div>
          </div>
        </footer>
      </body>
    </html>
  )
}
