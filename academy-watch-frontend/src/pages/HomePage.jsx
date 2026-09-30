import { useEffect, useRef } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { InterestSignup } from '@/components/interest/InterestSignup'

const audiences = [
  { name: 'Clubs', title: 'A home for your club.', image: '/media/club-match.webp',
    copy: 'Claim your club, bring your squad together and keep your players’ development in view.',
    link: '/my-club', action: 'Claim your club' },
  { name: 'Players', title: 'Build a record of your game.', image: '/media/player-sundown.webp',
    copy: 'Set up your profile, share your highlights and keep the story of your football in one place.',
    link: '/onboarding/player', action: 'Start your player profile' },
  { name: 'Scouts', title: 'Follow the next step.', image: '/media/scout-stadium.webp',
    copy: 'Explore player records, compare the evidence and keep track of the players you want to follow.',
    link: '/scout', action: 'Open the scout desk' },
]

export function HomePage() {
  const video = useRef(null)
  const location = useLocation()
  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => {
      if (preference.matches) video.current?.pause()
      else video.current?.play().catch(() => {})
    }
    update()
    preference.addEventListener('change', update)
    return () => preference.removeEventListener('change', update)
  }, [])
  useEffect(() => {
    if (location.hash === '#early-access') document.getElementById('early-access')?.scrollIntoView()
  }, [location.hash])

  return (
    <div>
      <section className="dark relative isolate overflow-hidden bg-night text-chalk">
        <video ref={video} poster="/media/hero-poster.webp" muted loop playsInline aria-hidden="true"
          className="absolute inset-0 -z-20 h-full w-full object-cover" preload="metadata">
          <source src="/media/dribble.mp4" type="video/mp4" />
        </video>
        <div className="absolute inset-0 -z-10 bg-night/60" />
        <div className="floodlight-container py-24 sm:py-32 lg:py-40">
          <p className="eyebrow mb-7">Clubs · Players · Scouts</p>
          <h1 className="display max-w-4xl text-[56px] sm:text-[80px] lg:text-[96px]">
            Every player deserves to be <em className="text-gold">seen.</em>
          </h1>
          <p className="mt-8 max-w-xl text-base font-light leading-relaxed text-chalk/85 sm:text-lg">
            A home for your club. A record of your game. A clearer view of the next step.
            Football, with the people who know you at its heart.
          </p>
          <div className="mt-9 flex flex-wrap items-center gap-4">
            <Button asChild><Link to="/#early-access">Get early access <ArrowRight /></Link></Button>
            <Button variant="outline" asChild><Link to="/scout">Explore players</Link></Button>
          </div>
          <div className="mt-16 flex justify-between border-t border-border pt-5 sm:mt-24">
            <span className="eyebrow">The beautiful game, in view</span>
            <span className="eyebrow hidden sm:block">Your side of the touchline</span>
          </div>
        </div>
      </section>
      <section className="floodlight-container py-16 sm:py-24">
        <div className="flex flex-col justify-between gap-6 border-b border-ink pb-8 md:flex-row md:items-end">
          <div><p className="eyebrow mb-4">Three sides of the touchline</p>
            <h2 className="display text-4xl sm:text-5xl">One home for the whole game.</h2></div>
          <span className="eyebrow shrink-0">Available today</span>
        </div>
        {audiences.map((audience, index) => (
          <div key={audience.name} className="rule-row grid items-center gap-7 py-10 md:grid-cols-[.85fr_1.2fr_1fr] md:gap-12">
            <div><p className="eyebrow mb-4">0{index + 1} / {audience.name}</p>
              <h3 className="display text-4xl">{audience.title}</h3></div>
            <div><p className="max-w-md leading-relaxed text-muted-foreground">{audience.copy}</p>
              <Button className="mt-5" variant="outline" asChild><Link to={audience.link}>{audience.action} <ArrowRight /></Link></Button></div>
            <img src={audience.image} alt="" loading="lazy" width="480" height="280" className="aspect-[12/7] w-full rounded-lg object-cover" />
          </div>
        ))}
      </section>
      <section id="early-access" className="dark scroll-mt-6 bg-night text-chalk">
        <div className="floodlight-container grid gap-12 py-16 sm:py-24 md:grid-cols-2 md:gap-20">
          <div><p className="eyebrow mb-5">The next chapter</p>
            <h2 className="display text-5xl sm:text-6xl">Join us at kick-off.</h2>
            <p className="mt-6 max-w-md leading-relaxed text-muted-foreground">
              There’s more to come. Tell us your side of the game and we’ll keep you in the loop as Academy Watch grows.
            </p>
            <div className="mt-8 flex flex-wrap gap-6 text-sm">
              <Link className="underline underline-offset-4" to="/clubs">Clubs near you</Link>
              <Link className="underline underline-offset-4" to="/opportunities">Playing opportunities</Link>
            </div>
          </div>
          <InterestSignup feature="early_access" showRole className="self-center" />
        </div>
      </section>
    </div>
  )
}
