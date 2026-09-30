import { InterestSignup } from '@/components/interest/InterestSignup'

const FACTS = [
  ['When', 'The date, the time and how long it runs.'],
  ['Where', 'The ground and the pitch — no guesswork on the day.'],
  ['Who', 'Ages, positions and level, so you know it’s for you.'],
]

export function OpportunitiesTeaser() {
  return (
    <div className="bg-chalk text-ink">
      <section className="dark relative isolate overflow-hidden bg-night text-chalk">
        <img src="/media/player-sundown.webp" alt="" className="absolute inset-0 -z-20 h-full w-full object-cover" />
        <div className="absolute inset-0 -z-10 bg-night/60" />
        <div className="floodlight-container py-20 sm:py-28">
          <p className="eyebrow">Trials · open sessions · places to fill</p>
          <h1 className="display mt-5 max-w-4xl text-[52px] sm:text-[88px]">
            Room for your <em className="text-gold">next</em> step.
          </h1>
          <p className="mt-6 max-w-xl text-base leading-relaxed text-chalk/85 sm:text-lg">
            Opportunities, straight from the clubs that run them. Coming soon to The Academy Watch.
          </p>
        </div>
      </section>

      <div className="floodlight-container grid items-start gap-14 py-16 sm:py-20 lg:grid-cols-[minmax(0,1fr)_480px] lg:gap-[72px]">
        <article className="min-w-0 space-y-10">
          <div>
            <p className="eyebrow text-gold-text">What every opportunity will tell you</p>
            <div className="mt-5 grid border-y border-border sm:grid-cols-3">
              {FACTS.map(([label, body], index) => (
                <div
                  key={label}
                  className={`py-6 sm:px-6 ${index === 0 ? 'sm:pl-0' : ''} ${index < FACTS.length - 1 ? 'border-b border-border sm:border-b-0 sm:border-r' : ''}`}
                >
                  <div className="eyebrow">{label}</div>
                  <div className="display mt-2 text-[26px] leading-[1.15]">{body}</div>
                </div>
              ))}
            </div>
          </div>

          <p className="display max-w-2xl text-[26px] leading-[1.25] sm:text-[30px]">
            Clubs post the trials, open sessions and places they need to fill. You apply in about a minute,
            and your application goes straight to the coach.
          </p>

          <p className="max-w-2xl rounded-lg bg-chalk-2 px-5 py-4 text-[15px] leading-relaxed text-ink/80">
            Under-18s will apply through a parent or guardian. Young players’ details will stay private with the
            club and never appear on public pages.
          </p>
        </article>

        <aside className="rounded-[10px] border border-border bg-[#FBFAF6] p-6 sm:p-10">
          <h2 className="display text-[40px] leading-none sm:text-[44px]">Hear first</h2>
          <p className="mt-3 text-[15px] text-muted-foreground">
            Leave your email and we’ll tell you when opportunities open. Takes a few seconds.
          </p>
          <InterestSignup feature="opportunities" showRole className="mt-8" />
        </aside>
      </div>
    </div>
  )
}
