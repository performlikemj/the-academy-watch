/**
 * ComingSoon props: feature, title, lede (required strings), bullets (optional
 * string[]), image (optional atmosphere image URL; decorative stock photo),
 * showRole (false), role (optional fixed role). Renders a full-page teaser.
 */
import { InterestSignup } from './InterestSignup'

export function ComingSoon({ feature, title, lede, bullets = [], image, showRole = false, role }) {
  return (
    <div>
      <section className="dark relative isolate overflow-hidden bg-night text-chalk">
        {image && <img src={image} alt="" className="absolute inset-0 -z-20 h-full w-full object-cover" />}
        {image && <div className="absolute inset-0 -z-10 bg-night/65" />}
        <div className="floodlight-container py-20 sm:py-28">
          <p className="eyebrow mb-6">Coming soon · The Academy Watch</p>
          <h1 className="display max-w-4xl text-[48px] sm:text-[80px]">{title}</h1>
          <p className="mt-7 max-w-xl text-base leading-relaxed text-chalk/85 sm:text-lg">{lede}</p>
        </div>
      </section>
      <section className="floodlight-container grid gap-12 py-16 md:grid-cols-2 md:gap-20 sm:py-24">
        <div>
          <p className="eyebrow mb-5">A little further down the touchline</p>
          <h2 className="display text-4xl sm:text-5xl">Be there when it opens.</h2>
          <ul className="mt-8">
            {bullets.map((bullet) => <li key={bullet} className="rule-row text-muted-foreground">{bullet}</li>)}
          </ul>
        </div>
        <div className="self-center rounded-lg border border-border p-6 sm:p-8">
          <h2 className="display mb-4 text-3xl">Keep me in the loop.</h2>
          <p className="mb-6 text-sm text-muted-foreground">Leave your email and we’ll let you know when this is ready.</p>
          <InterestSignup feature={feature} showRole={showRole} role={role} />
        </div>
      </section>
    </div>
  )
}
