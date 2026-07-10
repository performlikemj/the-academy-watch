import { useState } from 'react'
import { AtSign, Check, Copy, Download, Globe, MessageCircle, Share2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'
import {
    canNativeShare,
    copyShareLink,
    getPlayerShareUrl,
    getShareText,
    nativeShare,
    shareToFacebook,
    shareToWhatsApp,
    shareToX,
} from '@/lib/share'

import { generateStatCard } from './statCard'

/**
 * Share affordance for a player profile: native share, copy link, social
 * intents, and a branded downloadable stat card.
 *
 * variant="hero"  — visible button (Share label) for the claret hero band.
 * variant="ghost" — icon-only ghost button, for tighter contexts.
 */
export function ShareMenu({ playerId, playerName, profile, seasonTotals, position, variant = 'ghost' }) {
    const [copied, setCopied] = useState(false)
    const [downloading, setDownloading] = useState(false)

    const shareUrl = getPlayerShareUrl(playerId)
    const shareText = getShareText(playerName)
    const shareArgs = { url: shareUrl, playerName, text: shareText }
    const ariaLabel = `Share ${playerName || 'this player'}'s profile`

    const handleCopy = async (event) => {
        // Keep the menu open so the "Copied" confirmation is visible.
        event.preventDefault()
        const ok = await copyShareLink(shareArgs)
        if (ok) {
            setCopied(true)
            setTimeout(() => setCopied(false), 2000)
        }
    }

    const handleNativeShare = () => {
        nativeShare(shareArgs)
    }

    const handleDownloadStatCard = async () => {
        setDownloading(true)
        try {
            await generateStatCard({ playerName, profile, seasonTotals, position, shareUrl })
        } catch (err) {
            console.warn('Failed to generate stat card', err)
        } finally {
            setDownloading(false)
        }
    }

    const isHero = variant === 'hero'

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                {isHero ? (
                    <Button
                        variant="ghost"
                        aria-label={ariaLabel}
                        className={cn(
                            // h-11 = 44px Apple HIG touch target for the primary hero action
                            'h-11 gap-1.5 border border-border/60 bg-background/90 px-5 text-foreground shadow-sm backdrop-blur-sm',
                            'hover:bg-background dark:bg-background/80 dark:hover:bg-background/95'
                        )}
                    >
                        <Share2 className="size-4" aria-hidden="true" />
                        Share
                    </Button>
                ) : (
                    <Button variant="ghost" size="icon" className="h-11 w-11" aria-label={ariaLabel}>
                        <Share2 className="size-4" aria-hidden="true" />
                    </Button>
                )}
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
                {canNativeShare() && (
                    <DropdownMenuItem onClick={handleNativeShare} aria-label="Share via device">
                        <Share2 aria-hidden="true" />
                        Share…
                    </DropdownMenuItem>
                )}
                <DropdownMenuItem onSelect={handleCopy} aria-label="Copy share link">
                    {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
                    {copied ? 'Copied' : 'Copy link'}
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => shareToX(shareArgs)} aria-label="Share to X">
                    <AtSign aria-hidden="true" />
                    Share to X
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => shareToWhatsApp(shareArgs)} aria-label="Share to WhatsApp">
                    <MessageCircle aria-hidden="true" />
                    WhatsApp
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => shareToFacebook(shareArgs)} aria-label="Share to Facebook">
                    <Globe aria-hidden="true" />
                    Facebook
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                    onClick={handleDownloadStatCard}
                    disabled={downloading}
                    aria-label="Download stat card"
                >
                    <Download aria-hidden="true" />
                    {downloading ? 'Generating…' : 'Download stat card'}
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    )
}
