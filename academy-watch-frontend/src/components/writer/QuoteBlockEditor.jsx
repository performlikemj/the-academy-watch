import React, { useState, useEffect } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Quote, ExternalLink, Mail, MessageCircle, User, UserX } from 'lucide-react'

const SOURCE_TYPES = [
  {
    value: 'public_link',
    label: 'Public Link',
    icon: ExternalLink,
    description: 'Tweet, blog post, or public comment',
  },
  {
    value: 'direct_message',
    label: 'Direct Message',
    icon: MessageCircle,
    description: 'Twitter DM, Instagram DM, etc.',
  },
  {
    value: 'email',
    label: 'Email',
    icon: Mail,
    description: 'Email correspondence',
  },
  {
    value: 'personal',
    label: 'Personal Communication',
    icon: User,
    description: 'Phone call, in-person, voice message',
  },
  {
    value: 'anonymous',
    label: 'Anonymous Source',
    icon: UserX,
    description: 'Source wishes to remain unnamed',
  },
]

export function QuoteBlockEditor({ open, onOpenChange, block, onSave }) {
  const [formData, setFormData] = useState({
    quote_text: '',
    source_name: '',
    source_type: 'direct_message',
    source_platform: '',
    source_url: '',
    quote_date: '',
  })

  useEffect(() => {
    if (block) {
      setFormData({
        quote_text: block.quote_text || '',
        source_name: block.source_name || '',
        source_type: block.source_type || 'direct_message',
        source_platform: block.source_platform || '',
        source_url: block.source_url || '',
        quote_date: block.quote_date || '',
      })
    }
  }, [block])

  const handleSave = () => {
    onSave(formData)
  }

  const showUrlField = formData.source_type === 'public_link'
  const showPlatformField = ['public_link', 'direct_message'].includes(formData.source_type)
  const showSourceName = formData.source_type !== 'anonymous'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Quote className="h-5 w-5 text-amber-600" />
            {block?.quote_text ? 'Edit Quote' : 'Add Quote'}
          </DialogTitle>
          <DialogDescription>
            Add an attributed quote from a source
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Quote Text */}
          <div className="space-y-2">
            <Label htmlFor="quote_text">Quote *</Label>
            <Textarea
              id="quote_text"
              placeholder="Enter the quote text..."
              value={formData.quote_text}
              onChange={(e) => setFormData((prev) => ({ ...prev, quote_text: e.target.value }))}
              rows={3}
            />
          </div>

          {/* Source Type */}
          <div className="space-y-2">
            <Label>Source Type *</Label>
            <Select
              value={formData.source_type}
              onValueChange={(value) => setFormData((prev) => ({ ...prev, source_type: value }))}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SOURCE_TYPES.map((type) => (
                  <SelectItem key={type.value} value={type.value}>
                    <div className="flex items-center gap-2">
                      <type.icon className="h-4 w-4" />
                      <span>{type.label}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              {SOURCE_TYPES.find((t) => t.value === formData.source_type)?.description}
            </p>
          </div>

          {/* Source Name (hidden for anonymous) */}
          {showSourceName && (
            <div className="space-y-2">
              <Label htmlFor="source_name">Source Name *</Label>
              <Input
                id="source_name"
                placeholder="e.g., @ScoutAnalyst or John Smith"
                value={formData.source_name}
                onChange={(e) => setFormData((prev) => ({ ...prev, source_name: e.target.value }))}
              />
            </div>
          )}

          {/* Platform (for public_link and direct_message) */}
          {showPlatformField && (
            <div className="space-y-2">
              <Label htmlFor="source_platform">Platform</Label>
              <Input
                id="source_platform"
                placeholder="e.g., Twitter, Substack, Instagram"
                value={formData.source_platform}
                onChange={(e) =>
                  setFormData((prev) => ({ ...prev, source_platform: e.target.value }))
                }
              />
            </div>
          )}

          {/* URL (only for public_link) */}
          {showUrlField && (
            <div className="space-y-2">
              <Label htmlFor="source_url">URL</Label>
              <Input
                id="source_url"
                type="url"
                placeholder="https://twitter.com/..."
                value={formData.source_url}
                onChange={(e) => setFormData((prev) => ({ ...prev, source_url: e.target.value }))}
              />
            </div>
          )}

          {/* Quote Date */}
          <div className="space-y-2">
            <Label htmlFor="quote_date">Date (optional)</Label>
            <Input
              id="quote_date"
              type="month"
              value={formData.quote_date}
              onChange={(e) => setFormData((prev) => ({ ...prev, quote_date: e.target.value }))}
            />
            <p className="text-xs text-muted-foreground">When was this quote given?</p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={
              !formData.quote_text ||
              (formData.source_type !== 'anonymous' && !formData.source_name)
            }
          >
            Save Quote
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default QuoteBlockEditor
