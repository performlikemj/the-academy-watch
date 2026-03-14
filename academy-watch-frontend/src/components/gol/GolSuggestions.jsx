import { useState, useEffect } from 'react'
import { APIService } from '@/lib/api'
import { MessageCircle } from 'lucide-react'

export function GolSuggestions({ onSelect }) {
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
    <div className="flex flex-col items-center justify-center h-full py-8">
      <MessageCircle className="h-12 w-12 text-muted-foreground mb-4" />
      <h3 className="text-lg font-semibold mb-2">GOL Assistant</h3>
      <p className="text-sm text-muted-foreground mb-6 text-center">
        Ask me about players, academy pathways, career journeys, and more
      </p>
      <div className="grid gap-2 w-full max-w-sm">
        {suggestions.map((s, i) => (
          <button
            key={i}
            type="button"
            onClick={() => onSelect(s)}
            className="w-full rounded-lg border bg-card text-card-foreground shadow-sm cursor-pointer hover:bg-muted/50 transition-colors p-3 text-sm text-left"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}
