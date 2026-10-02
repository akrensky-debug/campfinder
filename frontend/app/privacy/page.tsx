import type { Metadata } from 'next'
import { LegalPage } from '@/components/LegalPage'
import { COMPANY, POLICY_UPDATED, SUPPORT_EMAIL } from '@/lib/site'

// DRAFT for founder and counsel review before the ChatGPT and Claude listings go live.
// Check: the legal entity name, processors list, retention periods, whether request-info
// messages are forwarded to camps, and state-law notices (e.g. California, Connecticut).

export const metadata: Metadata = {
  title: 'Privacy Policy | CampFinder',
  description: 'What CampFinder collects, why, who we share it with, and how to delete it.',
}

export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy Policy" updated={POLICY_UPDATED}>
      <p>
        CampFinder is made by {COMPANY} (&quot;we&quot;). It helps parents find and plan kids&apos; summer
        camps. This policy explains what we collect, why, who we share it with, and the choices you have.
        We collect as little as we can, we never sell personal information, and we don&apos;t show ads.
      </p>

      <h2>CampFinder in ChatGPT and Claude</h2>
      <p>
        When you use CampFinder inside ChatGPT or Claude, the assistant sends us only the search
        details it fills in for you: a town, a child&apos;s age, interests, dates, budget and needs such
        as extended care. We use them to return camps. We do not receive your conversation, your name,
        your email or your account with OpenAI or Anthropic, and we don&apos;t ask for them.
      </p>
      <ul>
        <li>Searches that find nothing are saved anonymously (town, ages, interests, weeks, budget) so we know where to add camps.</li>
        <li>Our servers keep standard request logs, including IP addresses, for security and rate limiting.</li>
        <li>Links back to CampFinder are tagged with where you came from (for example, <code>utm_source=chatgpt</code>) so we can count visits. They carry no personal details beyond the search you asked for.</li>
        <li>OpenAI and Anthropic handle your conversations under their own privacy policies.</li>
      </ul>

      <h2>On the CampFinder website</h2>
      <ul>
        <li><strong>Planning chat and family profile.</strong> What you tell the planner (your town, your kids&apos; first names, ages and interests, dates, budget and notes) is stored as your family profile and calendar so it can plan with you. Chat messages are processed by Anthropic&apos;s Claude model to produce answers.</li>
        <li><strong>Account.</strong> If you sign in, we store your email address to send sign-in links and keep your family attached to your account.</li>
        <li><strong>Info kit.</strong> Details you add to the info kit (contacts, pickups, insurance, medical notes) are encrypted before storage, are never sent to the AI model, and are shared only through links you create, which you can revoke. Every opening of a shared link is logged so you can see it.</li>
        <li><strong>Requests to camps and emails.</strong> If you request information or ask us to email results, we store your email, first name and what you searched for. If you ask a camp for information, we share your contact details and message with that camp.</li>
        <li><strong>Usage.</strong> We record page views and actions with a random session identifier stored in your browser, to improve the site.</li>
      </ul>

      <h2>Children</h2>
      <p>
        CampFinder is for parents and guardians. It is not directed to children, and we do not knowingly
        collect information from children under 13. Information about a child is provided by their
        parent or guardian, who can view or delete it at any time.
      </p>

      <h2>Who we share it with</h2>
      <p>We use service providers to run CampFinder, under contracts that limit their use of the data:</p>
      <ul>
        <li>Supabase (database and sign-in), Railway (servers) and Vercel (website hosting)</li>
        <li>Anthropic (the AI model behind the planning chat)</li>
        <li>Resend (email) and Stripe (payments by camps, not parents)</li>
      </ul>
      <p>
        We share information with a camp only when you ask us to, and with authorities only when the
        law requires it. If {COMPANY} is acquired, this policy continues to apply to information collected under it.
      </p>

      <h2>Your choices</h2>
      <ul>
        <li>Delete your family, calendar and info kit from your account page, or email us and we will delete them.</li>
        <li>Reset your private calendar link at any time; the old one stops working.</li>
        <li>Revoke any info kit share link at any time.</li>
        <li>Ask us what we hold about you, or ask us to correct it, at <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>.</li>
      </ul>

      <h2>Keeping it safe and how long we keep it</h2>
      <p>
        Data is encrypted in transit, and info kits are also encrypted at rest with a key held separately
        from the database. We keep family information while your family exists on CampFinder and delete
        it when you delete it. Anonymous search statistics and server logs are kept to run and improve the service.
      </p>

      <h2>Changes and contact</h2>
      <p>
        If we change this policy we will update the date above, and tell signed-in parents about material
        changes. Questions: <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>.
      </p>
    </LegalPage>
  )
}
