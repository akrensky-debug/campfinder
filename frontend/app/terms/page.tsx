import type { Metadata } from 'next'
import { LegalPage } from '@/components/LegalPage'
import { COMPANY, POLICY_UPDATED, SUPPORT_EMAIL } from '@/lib/site'

// DRAFT for founder and counsel review: governing law, liability cap and dispute terms
// are deliberately left general until counsel sets them.

export const metadata: Metadata = {
  title: 'Terms of Service | CampFinder',
  description: 'The terms for using CampFinder on the web and inside ChatGPT and Claude.',
}

export default function TermsPage() {
  return (
    <LegalPage title="Terms of Service" updated={POLICY_UPDATED}>
      <p>
        These terms cover your use of CampFinder, made by {COMPANY}, on our website and inside
        assistants such as ChatGPT and Claude. By using CampFinder you agree to them.
      </p>

      <h2>What CampFinder is</h2>
      <p>
        CampFinder helps parents find, compare and plan kids&apos; summer camps. We are not a camp, we don&apos;t
        run any program, and we don&apos;t take registrations or payments from parents. You register with
        each camp directly, on the camp&apos;s terms.
      </p>

      <h2>Camp information</h2>
      <p>
        We collect camp details from camps and public sources and mark which details are verified.
        Dates, prices, availability and policies can change, and unverified details may be wrong.
        Always confirm with the camp before you register or pay. CampFinder is provided &quot;as is&quot; and
        we are not responsible for a camp&apos;s programs, staff, safety or decisions.
      </p>

      <h2>AI answers</h2>
      <p>
        The planning chat, and assistants that use CampFinder, generate answers with AI. They can make
        mistakes. Use them as a starting point and check what matters with the camp.
      </p>

      <h2>Your account and information</h2>
      <p>
        Keep your sign-in email secure. You are responsible for what you share through info kit links.
        You can delete your family information at any time. Our <a href="/privacy">Privacy Policy</a>{' '}
        explains how we handle it.
      </p>

      <h2>Fair use</h2>
      <p>
        Don&apos;t misuse CampFinder: no scraping or bulk copying of camp data, no attempts to break or
        overload the service, and no false information about camps. Partners who want the data can use
        the <a href="/operators">Activity API</a> under its own terms.
      </p>

      <h2>Changes and contact</h2>
      <p>
        We may update these terms and will change the date above when we do. Questions:{' '}
        <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>.
      </p>
    </LegalPage>
  )
}
