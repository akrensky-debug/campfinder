"use client"

import React from 'react'
import { Events } from '@/lib/analytics'

export default function OperatorsPage() {
  return (
    <div className="max-w-4xl mx-auto px-4 py-16">
      <h1 className="text-4xl font-extrabold text-gray-900 mb-4">
        Get discovered by the parents who are already searching
      </h1>
      <p className="text-lg text-gray-500 max-w-2xl mx-auto">
        CampFinder is built for AI-first discovery.
      </p>
      <div className="grid md:grid-cols-2 gap-6 mb-20">
        <div className="bg-white border border-gray-200 rounded-2xl p-8 flex flex-col">
          <div className="text-3xl mb-3">camp</div>
          <h2 className="text-xl font-bold text-gray-900 mb-2">List your camp</h2>
          <p className="text-gray-500 text-sm flex-1 mb-6">
            Not yet on CampFinder? Submit your camp for free.
          </p>
          <a
            href="/operators/submit"
            onClick={() => Events.campSubmissionStarted()}
            className="block bg-brand-600 hover:bg-brand-700 text-white font-bold px-5 py-3 rounded-xl text-center transition-colors"
          >
            Submit your camp
          </a>
        </div>
        <div className="bg-white border border-gray-200 rounded-2xl p-8 flex flex-col">
          <div className="text-3xl mb-3">check</div>
          <h2 className="text-xl font-bold text-gray-900 mb-2">Claim your listing</h2>
          <p className="text-gray-500 text-sm flex-1 mb-6">
            Already listed? Claim your camp to update sessions and pricing.
          </p>
          <a
            href="/operators/claim"
            onClick={() => Events.claimFlowStarted("operator_page")}
            className="block border border-brand-600 text-brand-600 font-bold px-5 py-3 rounded-xl text-center transition-colors"
          >
            Claim your listing
          </a>
        </div>
      </div>
    </div>
  )
}
