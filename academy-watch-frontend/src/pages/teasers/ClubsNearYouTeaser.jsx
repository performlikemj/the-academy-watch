import { ComingSoon } from '@/components/interest/ComingSoon'

export function ClubsNearYouTeaser() {
  return <ComingSoon feature="clubs_near_you" title="Your game starts close to home."
    lede="We’re building a simpler way to find clubs and academies near you. A place to understand your options and take the next step."
    bullets={['Discover local clubs and the football they offer.', 'Find a place that fits your stage of the game.', 'Get a clear route to a conversation with the club.']}
    image="/media/city-pitch.webp" />
}
