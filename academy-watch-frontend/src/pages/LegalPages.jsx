import { Link } from 'react-router-dom'
import { LegalPageLayout } from '@/components/layouts/LegalPageLayout'

const EFFECTIVE_DATE = '2026-08-09'

export function TermsPage() {
  return (
    <LegalPageLayout title="Terms of Service" effectiveDate={EFFECTIVE_DATE}>
      <p>
        The Academy Watch (&quot;the Service&quot;, &quot;we&quot;, &quot;us&quot;) is operated by <strong>By Way of MJ LLC</strong>, 418 Broadway, Ste R, Albany, NY 12207, USA. By using theacademywatch.com or The Academy Watch iOS app, you agree to these terms.
      </p>

      <section>
        <h2>1. What the Service is</h2>
        <p>
          The Academy Watch tracks the careers of football (soccer) academy players using publicly available sports data, publishes newsletters and statistics, and — for verified users — provides a consent-based introduction service between scouts and adult players.
        </p>
      </section>

      <section>
        <h2>2. Accounts</h2>
        <p>
          Signing in with your email creates an account. You are responsible for access to your email inbox. You can delete your account at any time from the app or website; deletion is immediate and irreversible.
        </p>
      </section>

      <section>
        <h2>3. Adults only for participation</h2>
        <p>
          Browsing public content requires no account. <strong>Participation features — claiming a player profile, scout verification, and introductions — are for adults (18+) only.</strong> We refuse profile claims where we cannot establish an adult date of birth.
        </p>
      </section>

      <section>
        <h2>4. Player profile claims</h2>
        <p>
          If you claim a profile you must be the player shown or their authorized representative, and every statement you make (including your contract status) must be true. We check claims against our own data: <strong>where our records indicate a player is contracted to a club, scout contact is routed through the club regardless of self-reported status.</strong> Misrepresentation is grounds for removal of the claim and the account.
        </p>
      </section>

      <section>
        <h2>5. Scout verification</h2>
        <p>
          Scout status is granted after human review of your application and can be revoked at any time for misconduct. Verified status is not an endorsement.
        </p>
      </section>

      <section>
        <h2>6. Introductions and messaging</h2>
        <p>
          Introductions happen only through the Service. A conversation opens only after the player accepts, and — where a club is involved — after club consent. You agree not to move contact off-platform to bypass consent, not to solicit money from players or their families (&quot;never pay to be scouted&quot;), and to make only truthful attestations about club permission. We may notify clubs of contact requests involving their players.
        </p>
      </section>

      <section>
        <h2>7. Content and conduct</h2>
        <p>
          You keep ownership of content you submit and grant us a license to host and display it on the Service. The <Link to="/community-rules">Community Rules</Link> are part of these terms. We may remove content, restrict features, suspend, or ban accounts that break them. You can report content and block users in the app; we aim to act on reports within 48 hours.
        </p>
      </section>

      <section>
        <h2>8. Sports data</h2>
        <p>
          Player statistics and career data come from third-party sources and public records. They are provided &quot;as is&quot; for informational purposes; we do not guarantee accuracy or completeness, and nothing on the Service is betting, financial, or professional advice. Players (or their representatives) may request removal of their profile at any time via the in-app form or <Link to="/support">support</Link>.
        </p>
      </section>

      <section>
        <h2>9. Disclaimers and liability</h2>
        <p>
          The Service is provided &quot;as is&quot; without warranties of any kind. To the maximum extent permitted by law, By Way of MJ LLC is not liable for indirect, incidental, special, consequential, or punitive damages, or any loss of opportunity, arising from use of the Service — including outcomes of introductions. Our total liability for any claim is limited to USD 100.
        </p>
      </section>

      <section>
        <h2>10. Changes and termination</h2>
        <p>
          We may update these terms; material changes will be posted here with a new effective date, and continued use is acceptance. We may suspend or end the Service or your access to it for breach of these terms.
        </p>
      </section>

      <section>
        <h2>11. Governing law</h2>
        <p>
          These terms are governed by the laws of the State of New York, USA, without regard to conflict-of-law rules. Courts located in New York have exclusive jurisdiction, except where the law of your country of residence grants you non-waivable rights or venue.
        </p>
      </section>

      <section>
        <h2>12. Contact</h2>
        <p>
          By Way of MJ LLC · 418 Broadway, Ste R, Albany, NY 12207, USA · <a href="mailto:mj@bywayofmj.com">mj@bywayofmj.com</a>
        </p>
      </section>
    </LegalPageLayout>
  )
}

export function PrivacyPage() {
  return (
    <LegalPageLayout title="Privacy Policy" effectiveDate={EFFECTIVE_DATE}>
      <p>
        By Way of MJ LLC (418 Broadway, Ste R, Albany, NY 12207, USA) operates The Academy Watch. This policy covers theacademywatch.com and The Academy Watch iOS app.
      </p>

      <section>
        <h2>What we collect</h2>
        <ul>
          <li><strong>Account data</strong>: your email address and an account identifier, created when you sign in.</li>
          <li><strong>Content you submit</strong>: profile claims, messages, introduction requests, reports, watchlists and lists, verification applications, newsletter subscriptions.</li>
          <li><strong>Technical logs</strong>: standard server logs (IP address, timestamps, request data) kept for security and debugging.</li>
        </ul>
        <p>
          We do <strong>not</strong> run advertising, tracking, or third-party analytics, and we do <strong>not</strong> sell personal data.
        </p>
      </section>

      <section>
        <h2>Player sports data</h2>
        <p>
          The Service publishes football performance data about academy and professional players (appearances, goals, clubs, transfers) sourced from licensed sports-data providers and public records. This is journalistic, public-interest sports reporting. Any player — or their authorized representative — can request profile removal using the in-app &quot;Request profile removal&quot; form or by emailing support; removal requests are handled without confirming whether a profile exists.
        </p>
      </section>

      <section>
        <h2>Who processes data for us</h2>
        <ul>
          <li><strong>Supabase</strong> (database hosting, USA)</li>
          <li><strong>Microsoft Azure</strong> (application hosting, USA)</li>
          <li><strong>Mailgun</strong> (email delivery)</li>
          <li><strong>Stripe</strong> (payments — contributing writers only)</li>
          <li><strong>API-Football</strong> (sports data source — receives no personal account data)</li>
          <li><strong>OpenAI / OpenRouter / Groq</strong> (newsletter text generation — receives sports data, not your account data)</li>
        </ul>
      </section>

      <section>
        <h2>Retention and deletion</h2>
        <p>
          Account data is kept until you delete your account — available in-app and immediate. Messages and reports connected to safety investigations may be retained as required for legal compliance and platform safety. You can export a copy of your data in-app at any time (&quot;Export my data&quot;).
        </p>
      </section>

      <section>
        <h2>Your rights</h2>
        <p>
          Access, export, correction, deletion, and objection. Export and deletion are self-serve in the app; for anything else email <a href="mailto:mj@bywayofmj.com">mj@bywayofmj.com</a>. If you are in the UK or EU, these include your UK/EU GDPR rights; our lawful bases are consent (account features), contract (providing the Service), and legitimate interest (public-interest sports reporting and platform safety). Data is processed in the United States.
        </p>
      </section>

      <section>
        <h2>Children</h2>
        <p>
          Account participation features are for adults (18+). We do not knowingly hold accounts for minors; if you believe a minor holds an account, email us and we will delete it. Public sports statistics about youth players are subject to the removal rights described above.
        </p>
      </section>

      <section>
        <h2>Changes</h2>
        <p>Material changes will be posted here with a new effective date.</p>
      </section>
    </LegalPageLayout>
  )
}

export function CommunityRulesPage() {
  return (
    <LegalPageLayout title="Community Rules">
      <p>
        These rules apply to everyone using The Academy Watch. They exist to keep young players safe. Breaking them can mean content removal, loss of verified status, suspension, or a permanent ban — and where the law requires it, referral to authorities.
      </p>

      <ol>
        <li><strong>Never pay to be scouted — never charge to scout.</strong> Legitimate scouts and clubs never ask players or families for money. Report anyone who does, immediately.</li>
        <li><strong>Adults only.</strong> Participation features are for people 18 and over. Do not attempt to contact minors through or around the platform.</li>
        <li><strong>Go through clubs.</strong> Where a player is contracted, contact goes through the club. Do not ask players to bypass club consent or move conversations off-platform to avoid it.</li>
        <li><strong>Tell the truth.</strong> Claims, attestations, verification applications, and outcome reports must be honest.</li>
        <li><strong>No harassment.</strong> No threats, hate, sexual content, persistent unwanted contact, or doxxing. One clear &quot;no&quot; is enough.</li>
        <li><strong>No impersonation.</strong> Do not claim profiles that are not yours or pretend to represent a club or organization you do not.</li>
        <li><strong>Use the tools.</strong> Report abusive content from any message or profile; block anyone you no longer want to hear from. Blocking is mutual and permanent until you undo it.</li>
      </ol>

      <p>
        We review reports and aim to act <strong>within 48 hours</strong>. Emergencies involving a child&apos;s safety should also go to your local authorities.
      </p>
    </LegalPageLayout>
  )
}

export function SupportPage() {
  return (
    <LegalPageLayout title="Support">
      <p>
        <strong>Contact:</strong> <a href="mailto:mj@bywayofmj.com">mj@bywayofmj.com</a> — we aim to reply within 48 hours.
      </p>

      <section>
        <p><strong>Common requests</strong></p>
        <ul>
          <li><strong>Delete my account</strong> — in the app: Account → Delete account. Immediate and irreversible.</li>
          <li><strong>Export my data</strong> — in the app: Account → Export my data.</li>
          <li><strong>Remove a player profile</strong> — on the player&apos;s page choose &quot;Request profile removal…&quot;, or email us. We handle removal requests without confirming whether a profile exists.</li>
          <li><strong>Report content or a user</strong> — use Report on any message or profile, or email us. Safety reports are prioritized and handled within 48 hours.</li>
          <li><strong>Scout verification status</strong> — Account → Scout verification shows your application status; decisions are emailed.</li>
        </ul>
      </section>

      <p><strong>Company</strong>: By Way of MJ LLC · 418 Broadway, Ste R, Albany, NY 12207, USA</p>
    </LegalPageLayout>
  )
}
