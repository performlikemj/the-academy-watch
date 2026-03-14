import React, { useState, useEffect, useCallback } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Link2, Newspaper, Video, Share2, BarChart3, Globe, Plus, Loader2, Check, ExternalLink } from 'lucide-react'
import { APIService } from '@/lib/api'
import { isYouTubeUrl } from '@/lib/youtube'
import { VideoEmbed } from '@/components/VideoEmbed'

const TYPE_META = {
  article:   { label: 'Article',   icon: Newspaper },
  highlight: { label: 'Highlight', icon: Video },
  social:    { label: 'Social',    icon: Share2 },
  stats:     { label: 'Stats',     icon: BarChart3 },
  other:     { label: 'Other',     icon: Globe },
}

function LinkTypeIcon({ type, className }) {
  const Icon = TYPE_META[type]?.icon || Globe
  return <Icon className={className} />
}

export function PlayerLinksSection({ playerId }) {
  const [links, setLinks] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [url, setUrl] = useState('')
  const [title, setTitle] = useState('')
  const [linkType, setLinkType] = useState('article')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState(null)

  const isLoggedIn = !!APIService.userToken

  const loadLinks = useCallback(async () => {
    try {
      const data = await APIService.getPlayerLinks(playerId)
      setLinks(Array.isArray(data) ? data : [])
    } catch {
      // silently fail
    } finally {
      setLoading(false)
    }
  }, [playerId])

  useEffect(() => {
    loadLinks()
  }, [loadLinks])

  const handleSubmit = async (e) => {
    e.preventDefault()
    const trimmedUrl = url.trim()
    if (!trimmedUrl || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      await APIService.submitPlayerLink(playerId, {
        url: trimmedUrl,
        title: title.trim() || undefined,
        link_type: linkType,
      })
      setSubmitted(true)
      setUrl('')
      setTitle('')
      setLinkType('article')
      setTimeout(() => {
        setSubmitted(false)
        setShowForm(false)
      }, 2000)
    } catch (err) {
      setError(err.message || 'Failed to submit link')
    } finally {
      setSubmitting(false)
    }
  }

  // Group links by type, with highlights first
  const grouped = links.reduce((acc, link) => {
    const t = link.link_type || 'other'
    if (!acc[t]) acc[t] = []
    acc[t].push(link)
    return acc
  }, {})

  // Sort so highlights appear first
  const sortedTypes = Object.keys(grouped).sort((a, b) => {
    if (a === 'highlight') return -1
    if (b === 'highlight') return 1
    return 0
  })

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            <Link2 className="h-4 w-4" />
            Links
            {links.length > 0 && (
              <span className="text-sm font-normal text-muted-foreground">({links.length})</span>
            )}
          </CardTitle>
          {isLoggedIn && !showForm && (
            <Button variant="outline" size="sm" onClick={() => setShowForm(true)} className="gap-1.5">
              <Plus className="h-3.5 w-3.5" />
              Add Link
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Submit form */}
        {showForm && (
          <form onSubmit={handleSubmit} className="p-4 bg-secondary rounded-lg space-y-3">
            {submitted ? (
              <div className="flex items-center gap-2 text-sm text-green-600 py-2">
                <Check className="h-4 w-4" />
                Submitted for review
              </div>
            ) : (
              <>
                <Input
                  placeholder="URL (e.g. https://...)"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  type="url"
                  required
                  maxLength={500}
                />
                <Input
                  placeholder="Title (optional)"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  maxLength={200}
                />
                <Select value={linkType} onValueChange={setLinkType}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(TYPE_META).map(([key, { label }]) => (
                      <SelectItem key={key} value={key}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {error && <p className="text-xs text-red-500">{error}</p>}
                <div className="flex gap-2 justify-end">
                  <Button type="button" variant="ghost" size="sm" onClick={() => setShowForm(false)}>
                    Cancel
                  </Button>
                  <Button type="submit" size="sm" disabled={!url.trim() || submitting}>
                    {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1.5" /> : null}
                    Submit
                  </Button>
                </div>
              </>
            )}
          </form>
        )}

        {/* Links list */}
        {loading ? (
          <div className="flex justify-center py-6">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground/70" />
          </div>
        ) : links.length === 0 && !showForm ? (
          <p className="text-sm text-muted-foreground text-center py-4">
            No links yet.{isLoggedIn ? ' Share a relevant article or highlight.' : ' Sign in to submit links.'}
          </p>
        ) : (
          <div className="space-y-3">
            {sortedTypes.map((type) => {
              const items = grouped[type]
              return (
                <div key={type}>
                  <div className="flex items-center gap-1.5 mb-2">
                    <LinkTypeIcon type={type} className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                      {TYPE_META[type]?.label || type}
                    </span>
                  </div>
                  <div className="space-y-1.5">
                    {items.map((link) => {
                      if (type === 'highlight' && isYouTubeUrl(link.url)) {
                        return (
                          <div key={link.id} className="space-y-1.5">
                            {link.title && (
                              <p className="text-sm font-medium text-foreground/80 px-1">{link.title}</p>
                            )}
                            <VideoEmbed url={link.url} title={link.title} />
                          </div>
                        )
                      }
                      return (
                        <a
                          key={link.id}
                          href={link.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-secondary transition-colors group text-sm"
                        >
                          <ExternalLink className="h-3.5 w-3.5 text-muted-foreground/70 group-hover:text-primary flex-shrink-0" />
                          <span className="text-foreground/80 group-hover:text-primary truncate flex-1">
                            {link.title || link.url}
                          </span>
                          {link.upvotes > 0 && (
                            <Badge variant="secondary" className="text-xs px-1.5 py-0">{link.upvotes}</Badge>
                          )}
                        </a>
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* Sign-in prompt */}
        {!isLoggedIn && links.length > 0 && (
          <div className="pt-2 border-t text-center">
            <p className="text-sm text-muted-foreground">Sign in to submit links</p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default PlayerLinksSection
