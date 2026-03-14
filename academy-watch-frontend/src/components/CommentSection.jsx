import React, { useState, useEffect, useCallback } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Textarea } from '@/components/ui/textarea'
import { MessageSquare, Loader2, Send } from 'lucide-react'
import { APIService } from '@/lib/api'

function relativeTime(dateStr) {
  if (!dateStr) return ''
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  const seconds = Math.floor((now - then) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`
  return new Date(dateStr).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function CommentSection({ newsletterId, playerId, title = 'Comments' }) {
  const [comments, setComments] = useState([])
  const [loading, setLoading] = useState(true)
  const [body, setBody] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  const isLoggedIn = !!APIService.userToken

  const loadComments = useCallback(async () => {
    try {
      let data
      if (newsletterId) {
        data = await APIService.listNewsletterComments(newsletterId)
      } else if (playerId) {
        data = await APIService.listPlayerComments(playerId)
      }
      setComments(Array.isArray(data) ? data : [])
    } catch {
      // Silently fail on load
    } finally {
      setLoading(false)
    }
  }, [newsletterId, playerId])

  useEffect(() => {
    loadComments()
  }, [loadComments])

  const handleSubmit = async (e) => {
    e.preventDefault()
    const trimmed = body.trim()
    if (!trimmed || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      if (newsletterId) {
        await APIService.createNewsletterComment(newsletterId, trimmed)
      } else if (playerId) {
        await APIService.createPlayerComment(playerId, trimmed)
      }
      setBody('')
      await loadComments()
    } catch (err) {
      setError(err.message || 'Failed to post comment')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <MessageSquare className="h-4 w-4" />
          {title}
          {comments.length > 0 && (
            <span className="text-sm font-normal text-muted-foreground">({comments.length})</span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Comment list */}
        {loading ? (
          <div className="flex justify-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground/70" />
          </div>
        ) : comments.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-4">No comments yet. Be the first to share your thoughts.</p>
        ) : (
          <div className="space-y-3">
            {comments.map((c) => (
              <div key={c.id} className="flex gap-3">
                <Avatar className="h-8 w-8 flex-shrink-0">
                  <AvatarFallback className="text-xs bg-secondary text-muted-foreground">
                    {(c.author_display_name || c.author_name || '?').substring(0, 2).toUpperCase()}
                  </AvatarFallback>
                </Avatar>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-sm font-medium text-foreground truncate">
                      {c.author_display_name || c.author_name || 'Anonymous'}
                    </span>
                    <span className="text-xs text-muted-foreground/70 flex-shrink-0">
                      {relativeTime(c.created_at)}
                    </span>
                  </div>
                  <p className="text-sm text-foreground/80 whitespace-pre-wrap break-words">{c.body}</p>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Comment form */}
        {isLoggedIn ? (
          <form onSubmit={handleSubmit} className="pt-3 border-t space-y-2">
            <Textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Add a comment..."
              className="min-h-[80px] resize-none text-sm"
              maxLength={2000}
            />
            {error && <p className="text-xs text-red-500">{error}</p>}
            <div className="flex justify-end">
              <Button
                type="submit"
                size="sm"
                disabled={!body.trim() || submitting}
                className="gap-1.5"
              >
                {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                Post
              </Button>
            </div>
          </form>
        ) : (
          <div className="pt-3 border-t text-center">
            <p className="text-sm text-muted-foreground">Sign in to join the discussion</p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default CommentSection
