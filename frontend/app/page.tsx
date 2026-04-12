'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'

const CAMP_TYPES = ['Any type', 'Day camp', 'Sleepaway', 'Specialty']
const CATEGORIES = ['Sports', 'Arts', 'STEM', 'Nature', 'Performing arts', 'Technology']

export default function HomePage() {
  const router = useRouter()
  const [location, setLocation] = useState('')
  const [age, setAge] = useState('')
  const [campType, setCampType] = useState('')
  const [loading, setLoading] = useState(false)

  function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    if (!location.trim()) return
    setLoading(true)
    const params = new URLSearchParams({ location })
    if (age) params.set('age', age)
    if (campType && campType !== 'Any type') params.set('camp_type', campType.toLowerCase().replace(' ', ''))
    router.push(`/search?${params.toString()}`)
  }

  return (
    <div>
      {/* Hero */}
      <section className="bg-gradient-to-br from-brand-700 via-brand-800 to-brand-900 text-white py-20 px-4">
        <div className="max-w-3xl mx-auto text-center">
          <h1 className="text-4xl md:text-5xl font-extrabold mb-4 leading-tight">
            There is finally a better way<br className="hidden md:block" /> to plan your kid's summer.
          </h1>
          <p className="text-brand-100 text-lg md:text-xl mb-10">
            Search verified camps by location, age, and interests. See real sessions and pricing. Request info in one click.
          </p>

          {/* Search form */}
          <form onSubmit={handleSearch} className="bg-white rounded-2xl p-2 shadow-2xl flex flex-col md:flex-row gap-2">
            <input
              type="text"
              placeholder="City or zip code (e.g. Providence, RI)"
              value={location}
              onChange={e => setLocation(e.target.value)}
              className="flex-1 px-4 py-3 text-gray-900 rounded-xl text-base outline-none"
              required
            />
            <input
              type="number"
              placeholder="Child's age"
              value={age}
              onChange={e => setAge(e.target.value)}
              min={3} max={18}
              className="w-full md:w-32 px-4 py-3 text-gray-900 rounded-xl text-base outline-none"
            />
            <select
              value={campType}
              onChange={e => setCampType(e.target.value)}
              className="w-full md:w-40 px-4 py-3 text-gray-700 rounded-xl text-base outline-none bg-white"
            >
              {CAMP_TYPES.map(t => <option key={t}>{t}</option>)}
            </select>
            <button
              type="submit"
              disabled={loading}
              className="bg-brand-600 hover:bg-brand-700 text-white font-bold px-6 py-3 rounded-xl transition-colors disabled:opacity-60 whitespace-nowrap"
            >
              {loading ? 'Searching...' : 'Find Camps →'}
            </button>
          </form>

          <p className="text-brand-200 text-sm mt-4">
            Covering Providence, Boston, NYC metro + more -- 2027 season
          </p>
        </div>
      </section>

      {/* How it works */}
      <section className="py-16 px-4 bg-white">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-2xl font-bold text-center mb-10 text-gray-900">How CampFinder works</h2>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              { icon: '🔍', title: 'Search by what matters', desc: 'Filter by location, age, type, price, transportation, meals, and more.' },
              { icon: '✅', title: 'Compare verified listings', desc: 'See trust scores, ACA accreditation, and freshness grades on every camp.' },
              { icon: '📅', title: 'Plan your whole summer', desc: 'Build a week-by-week schedule, spot gaps, and estimate total cost.' },
            ].map(step => (
              <div key={step.title} className="text-center p-6 rounded-2xl bg-gray-50">
                <div className="text-4xl mb-3">{step.icon}</div>
                <h3 className="font-semibold text-gray-900 mb-2">{step.title}</h3>
                <p className="text-gray-500 text-sm">{step.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Camp type quick links */}
      <section className="py-12 px-4 bg-gray-50">
        <div className="max-w-5xl mx-auto">
          <h2 className="text-2xl font-bold text-center mb-8 text-gray-900">Browse by type</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {[
              { label: '⚽ Sports Camps', q: 'sports' },
              { label: '🎨 Arts Camps', q: 'arts' },
              { label: '🤖 STEM Camps', q: 'STEM' },
              { label: '🌲 Nature Camps', q: 'nature' },
              { label: '🏕️ Sleepaway Camps', q: 'sleepaway' },
              { label: '🌟 Specialty Camps', q: 'specialty' },
            ].map(item => (
              <a
                key={item.q}
                href={`/search?location=Providence%2C+RI&category=${item.q}`}
                className="bg-white rounded-xl border border-gray-200 p-4 text-center font-medium text-gray-700 hover:border-brand-400 hover:text-brand-700 hover:shadow-sm transition-all"
              >
                {item.label}
              </a>
            ))}
          </div>
        </div>
      </section>

      {/* Operator CTA */}
      <section className="py-16 px-4 bg-brand-700 text-white">
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="text-3xl font-bold mb-3">The easiest way for camps to become discoverable in the AI economy.</h2>
          <p className="text-brand-100 text-lg mb-8">
            Structure your data. Verify your listing. Show up when parents ask Claude, ChatGPT, or Google about camps like yours.
          </p>
          <a
            href="/operators"
            className="inline-block bg-white text-brand-700 font-bold px-8 py-3 rounded-xl hover:bg-brand-50 transition-colors"
          >
            Claim or list your camp →
          </a>
        </div>
      </section>
    </div>
  )
}
