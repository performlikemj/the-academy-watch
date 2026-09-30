import { useState, useEffect } from 'react'
import { APIService } from '@/lib/api'

export function GolSuggestions({ onSelect, disabled = false }) {
  const [suggestions, setSuggestions] = useState([])

  useEffect(() => {
    APIService.getGolSuggestions()
      .then(data => setSuggestions(data.suggestions || []))
      .catch(() => setSuggestions([
        "Which Big 6 academy is producing the most first-team players?",
        "Show me all academy players from Arsenal",
        "Who are the top-performing academy players this season?",
        "Tell me about Chelsea\u2019s academy pipeline",
      ]))
  }, [])

  return (
    <div className="flex h-full flex-col justify-center gap-6 py-8">
      <div className="flex items-start gap-4">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-gold font-serif text-lg text-gold" aria-hidden="true">G</span>
        <div>
          <h3 className="display text-[1.75rem] leading-tight">GOL Assistant</h3>
          <p className="mt-1 text-[14.5px] leading-relaxed text-muted-dark">
            Ask me about players, academy pathways, career journeys, and more
          </p>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {suggestions.map((s, i) => (
          <button
            key={i}
            type="button"
            onClick={() => onSelect(s)}
            disabled={disabled}
            className="rounded-full border border-chalk/20 bg-transparent px-4 py-2.5 text-left text-[13.5px] leading-snug text-[#C9CFCB] transition-colors duration-150 hover:border-gold/60 hover:text-chalk disabled:cursor-not-allowed disabled:opacity-50"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}
