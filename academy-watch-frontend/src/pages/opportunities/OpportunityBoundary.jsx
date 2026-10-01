import { Component } from 'react'

export class OpportunityBoundary extends Component {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    if (this.state.failed) return <section className="p2-opportunities floodlight-container py-12" role="alert"><p>We could not display this opportunity. Please reload to try again.</p><button className="opp-button mt-4" onClick={() => window.location.reload()}>Reload</button></section>
    return this.props.children
  }
}
