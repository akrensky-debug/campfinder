'use client'

import { useState } from 'react'
import { submitCamp } from '@/lib/api'
import { Events } from '@/lib/analytics'

const CAMP_TYPES = ['day', 'sleepaway', 'specialty']
const CATEGORIES = [
  'arts', 'sports', 'stem', 'music', 'nature', 'academic',
  'language', 'dance', 'theater', 'coding', 'swimming', 'tennis',
  'basketball', 'soccer', 'leadership', 'adventure',
]

export default function SubmitCampPage() {
  const [step, setStep] = useState<'form' | 'done'>('form')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [form, setForm] = useState({
    name: '',
    city: '',
    state: '',
    camp_type: 'day',
    contact_email: '',
    contact_name: '',
    phone: '',
    website_url: '',
    description_short: '',
    age_min: '',
    age_max: '',
    price_per_week: '',
    categories: [] as string[],
  })

  function set(field: string, value: string) {
    setForm(f => ({ ...f, [field]: value }))
  }

  function toggleCategory(cat: string) {
    setForm(f => ({
      ...f,
      categories: f.categories.includes(cat)
        ? f.categories.filter(c => c !== cat)
        : [...f.categories, cat],
    }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError('')
    Events.campSubmissionStarted()
    try {
      await submitCamp({
        name: form.name,
        city: form.city,
        state: form.state,
        camp_type: form.camp_type,
        contact_email: form.contact_email,
        contact_name: form.contact_name || undefined,
        phone: form.phone || undefined,
        website_url: form.website_url || undefined,
        description_short: form.description_short || undefined,
        age_min: form.age_min ? Number(form.age_min) : undefined,
        age_max: form.age_max ? Number(form.age_max) : undefined,
        price_per_week: form.price_per_week ? Number(form.price_per_week) : undefined,
        primary_categories: form.categories.length > 0 ? form.categories : undefined,
      })
      setStep('done')
    } catch {
      setError('Submission failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  if (step === 'done') {
    return (
      <div className="max-w-lg mx-auto px-4 py-24 text-center">
        <div className="text-5xl mb-4">🎉</div>
        <h1 className="text-2xl font-extrabold text-gray-900 mb-3">Camp submitted!</h1>
        <p className="text-gray-500 text-sm mb-6">
          We'll review your listing and publish it within 1-2 business days.
          You'll receive a confirmation at <strong>{form.contact_email}</strong>.
        </p>
        <a href="/operators/claim" className="text-brand-600 underline text-sm">
          Already listed? Claim your listing to verify and update it.
        </a>
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-12">
      <nav className="text-sm text-gray-400 mb-8">
        <a href="/operators" className="hover:text-brand-600">← For camps</a>
      </nav>

      <div className="mb-8">
        <h1 className="text-3xl font-extrabold text-gray-900 mb-2">List your camp</h1>
        <p className="text-gray-500 text-sm">
          Free to submit. Your listing will be reviewed and published within 1-2 business days.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Basic info */}
        <section className="bg-white border border-gray-200 rounded-2xl p-6 space-y-4">
          <h2 className="font-bold text-gray-900">Camp basics</h2>

          <div>
            <label className="block text-sm text-gray-600 mb-1">Camp name *</label>
            <input
              type="text"
              required
              value={form.name}
              onChange={e => set('name', e.target.value)}
              className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm outline-none focus:border-brand-400"
              placeholder="e.g. Sunrise Day Camp"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm text-gray-600 mb-1">City *</label>
              <input
                type="text"
                required
                value={form.city}
                onChange={e => set('city', e.target.value)}
                className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm outline-none focus:border-brand-400"
                placeholder="e.g. Boston"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">State *</label>
              <input
                type="text"
                required
                maxLength={2}
                value={form.state}
                onChange={e => set('state', e.target.value.toUpperCase())}
                className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm outline-none focus:border-brand-400"
                placeholder="MA"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm text-gray-600 mb-1">Camp type *</label>
            <div className="flex gap-2 flex-wrap">
              {CAMP_TYPES.map(t => (
                <button
                  key={t}
                  type="button"
                  onClick={() => set('camp_type', t)}
                  className={`px-4 py-2 rounded-xl text-sm font-medium border transition-colors capitalize ${
                    form.camp_type === t
                      ? 'bg-brand-600 text-white border-brand-600'
                      : 'border-gray-200 text-gray-600 hover:border-brand-300'
                  }`}
                >
                  {t === 'day' ? 'Day Camp' : t === 'sleepaway' ? 'Sleepaway' : 'Specialty'}
                </button>
              ))}
            </div>
          </div>
        </section>

        {/* Contact */}
        <section className="bg-white border border-gray-200 rounded-2xl p-6 space-y-4">
          <h2 className="font-bold text-gray-900">Contact info</h2>

          <div>
            <label className="block text-sm text-gray-600 mb-1">Contact email *</label>
            <input
              type="email"
              required
              value={form.contact_email}
              onChange={e => set('contact_email', e.target.value)}
              className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm outline-none focus:border-brand-400"
              placeholder="director@yourcamp.com"
            />
            <p className="text-xs text-gray-400 mt-1">Used to verify ownership. Not shown publicly.</p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm text-gray-600 mb-1">Your name</label>
              <input
                type="text"
                value={form.contact_name}
                onChange={e => set('contact_name', e.target.value)}
                className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm outline-none focus:border-brand-400"
                placeholder="Jane Smith"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">Phone</label>
              <input
                type="tel"
                value={form.phone}
                onChange={e => set('phone', e.target.value)}
                className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm outline-none focus:border-brand-400"
                placeholder="(617) 555-0100"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm text-gray-600 mb-1">Camp website</label>
            <input
              type="url"
              value={form.website_url}
              onChange={e => set('website_url', e.target.value)}
              className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm outline-none focus:border-brand-400"
              placeholder="https://yourcamp.com"
            />
          </div>
        </section>

        {/* Details */}
        <section className="bg-white border border-gray-200 rounded-2xl p-6 space-y-4">
          <h2 className="font-bold text-gray-900">Camp details</h2>

          <div>
            <label className="block text-sm text-gray-600 mb-1">Short description</label>
            <textarea
              rows={3}
              value={form.description_short}
              onChange={e => set('description_short', e.target.value)}
              maxLength={300}
              className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm outline-none focus:border-brand-400 resize-none"
              placeholder="1-2 sentences describing your camp. This appears in search results."
            />
            <p className="text-xs text-gray-400 mt-1">{form.description_short.length}/300</p>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-sm text-gray-600 mb-1">Min age</label>
              <input
                type="number"
                min={3} max={18}
                value={form.age_min}
                onChange={e => set('age_min', e.target.value)}
                className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm outline-none focus:border-brand-400"
                placeholder="5"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">Max age</label>
              <input
                type="number"
                min={3} max={18}
                value={form.age_max}
                onChange={e => set('age_max', e.target.value)}
                className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm outline-none focus:border-brand-400"
                placeholder="16"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-600 mb-1">Price/week ($)</label>
              <input
                type="number"
                min={0}
                value={form.price_per_week}
                onChange={e => set('price_per_week', e.target.value)}
                className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm outline-none focus:border-brand-400"
                placeholder="650"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm text-gray-600 mb-2">Categories (select all that apply)</label>
            <div className="flex flex-wrap gap-2">
              {CATEGORIES.map(cat => (
                <button
                  key={cat}
                  type="button"
                  onClick={() => toggleCategory(cat)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors capitalize ${
                    form.categories.includes(cat)
                      ? 'bg-brand-600 text-white border-brand-600'
                      : 'border-gray-200 text-gray-600 hover:border-brand-300'
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>
        </section>

        {error && <p className="text-red-500 text-sm">{error}</p>}

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-brand-600 hover:bg-brand-700 text-white font-bold py-4 rounded-xl transition-colors disabled:opacity-60 text-base"
        >
          {loading ? 'Submitting...' : 'Submit camp for review →'}
        </button>

        <p className="text-xs text-center text-gray-400">
          By submitting you confirm you are authorized to list this camp.
          Listings are reviewed before publishing.
        </p>
      </form>
    </div>
  )
}
