import { Link } from 'react-router-dom'
import { ArrowUpRight } from 'lucide-react'
import { InterestSignup } from '@/components/interest/InterestSignup'

const FILTERS = ['Open opportunities', 'Under-16s', 'Girls & women', 'Adults', 'Film Room clubs']

const PROMISES = [
  ['Near you', 'Search by town or postcode and see the clubs within reach.'],
  ['What they offer', 'Squads, age groups and the football each club plays, from the club itself.'],
  ['A clear next step', 'Follow a club, or reach out with the club in the conversation.'],
]

export function ClubsNearYouTeaser() {
  return (
    <div className="dark bg-night text-chalk">
      <div className="floodlight-container pb-20 pt-14 sm:pb-24 sm:pt-20">
        <p className="eyebrow">Find a club · coming soon</p>
        <h1 className="display mt-5 max-w-4xl text-[52px] sm:text-[88px]">
          Clubs near <em className="text-gold">you</em>.
        </h1>
        <p className="mt-6 max-w-xl text-base leading-relaxed text-chalk/80 sm:text-lg">
          Your game starts close to home. We’re building a simpler way to find local clubs and academies,
          understand what they offer and take the next step.
        </p>

        <div className="mt-14 grid gap-12 lg:grid-cols-[minmax(0,560px)_minmax(0,1fr)] lg:gap-8">
          <div className="min-w-0">
            <p className="eyebrow text-muted-dark!">You’ll be able to filter by</p>
            <ul className="mt-4 flex flex-wrap gap-2.5" aria-label="Planned filters">
              {FILTERS.map((label) => (
                <li key={label} className="inline-flex h-9 items-center rounded-full border border-dashed border-chalk/30 px-4 text-sm text-chalk/75">
                  {label}
                </li>
              ))}
            </ul>

            <div className="mt-10 border-t border-border">
              {PROMISES.map(([title, body]) => (
                <div key={title} className="grid gap-1 border-b border-border py-5 sm:grid-cols-[180px_minmax(0,1fr)] sm:gap-6">
                  <span className="display text-[26px] leading-tight">{title}</span>
                  <span className="text-[15px] leading-relaxed text-muted-dark">{body}</span>
                </div>
              ))}
            </div>

            <div className="mt-10">
              <h2 className="display text-[34px]">Tell me when it opens.</h2>
              <p className="mt-2 text-sm text-muted-dark">One email when club search is ready. Nothing else.</p>
              <InterestSignup feature="clubs_near_you" showRole className="mt-6" />
            </div>
          </div>

          <div className="relative min-h-[360px] overflow-hidden rounded-lg bg-ink lg:min-h-[620px]">
            <img src="/media/city-pitch.webp" alt="" className="absolute inset-0 h-full w-full object-cover opacity-85" />
            <div className="absolute inset-0 bg-night/35" />
            <div className="absolute inset-x-4 bottom-4 flex flex-col gap-4 rounded-lg border border-chalk/15 bg-night/85 p-5 sm:inset-x-7 sm:bottom-7 sm:flex-row sm:items-center sm:gap-6 sm:p-6">
              <span className="flex-1">
                <span className="display block text-[28px] leading-tight">Run a club?</span>
                <span className="mt-1 block text-sm text-chalk/75">Claim your club’s page now so you’re on the map from day one.</span>
              </span>
              <Link to="/programs/claim" className="inline-flex h-11 shrink-0 items-center gap-2 self-start rounded-full border border-chalk/40 px-5 text-sm transition-colors hover:bg-chalk/10 sm:self-auto">
                Claim your club <ArrowUpRight className="h-4 w-4" />
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
