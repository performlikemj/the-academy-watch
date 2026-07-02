import * as React from 'react'
import { HelpCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/tooltip'

/**
 * HelpHint — a small inline "(?)" affordance that reveals a one-line explanation on
 * hover/focus/tap. Use it next to a label, badge, or term that a first-time user might
 * not understand. Keyboard- and screen-reader-accessible (it's a real <button>).
 *
 *   <span>Number agreement <HelpHint label="Number agreement">How consistent…</HelpHint></span>
 */
export function HelpHint({ children, label = 'More info', side = 'top', className, iconClassName }) {
    return (
        <Tooltip>
            <TooltipTrigger asChild>
                <button
                    type="button"
                    aria-label={label}
                    onClick={(e) => e.preventDefault()}
                    className={cn(
                        'inline-flex items-center justify-center align-middle text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-full',
                        className,
                    )}
                >
                    <HelpCircle className={cn('h-3.5 w-3.5', iconClassName)} />
                </button>
            </TooltipTrigger>
            <TooltipContent side={side} className="max-w-xs text-xs leading-relaxed">
                {children}
            </TooltipContent>
        </Tooltip>
    )
}

export default HelpHint
