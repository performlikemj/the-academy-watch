import { ComingSoon } from '@/components/interest/ComingSoon'
import '@/styles/floodlight-player.css'

export function PlayerApplicationsTeaser() {
  return <section className="fl-applications" aria-label="Player applications coming soon">
    <ComingSoon feature="player_applications" role="player" title="Your next chapter."
      lede="Applications will have a place here. Join the list to hear when you can take the next step towards a new club."
      image="/media/player-sundown.webp"
      bullets={['Find an opportunity that fits your game.', 'Keep your applications and replies together.']} />
  </section>
}
