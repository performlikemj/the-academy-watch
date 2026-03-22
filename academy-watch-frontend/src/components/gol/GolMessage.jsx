import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { GolDataCard } from './GolDataCard'
import { Loader2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

const TOOL_LABELS = {
  'run_analysis': 'Analysing data',
  'search_web': 'Searching the web',
}

/* ── Markdown component overrides for chat bubble styling ────────── */
const mdComponents = {
  h1: ({ children }) => <h2 className="text-sm font-semibold mt-3 mb-1 first:mt-0">{children}</h2>,
  h2: ({ children }) => <h2 className="text-sm font-semibold mt-3 mb-1 first:mt-0">{children}</h2>,
  h3: ({ children }) => <h3 className="text-xs font-semibold mt-2 mb-0.5">{children}</h3>,
  p: ({ children }) => <p className="mb-1.5 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  ul: ({ children }) => <ul className="list-disc ml-4 mb-1.5 space-y-0.5">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal ml-4 mb-1.5 space-y-0.5">{children}</ol>,
  li: ({ children }) => <li className="text-sm">{children}</li>,
  hr: () => <hr className="my-2 border-border/50" />,
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2 text-primary hover:text-primary/80">
      {children}
    </a>
  ),
  code: ({ inline, children }) =>
    inline !== false && !String(children).includes('\n')
      ? <code className="bg-foreground/10 rounded px-1 py-0.5 text-xs font-mono">{children}</code>
      : <pre className="bg-foreground/10 rounded p-2 text-xs font-mono overflow-x-auto my-1.5"><code>{children}</code></pre>,
  /* ── GFM Tables → Radix UI Table components ──────────────────── */
  table: ({ children }) => (
    <div className="overflow-x-auto my-2 rounded border border-border/50">
      <Table>{children}</Table>
    </div>
  ),
  thead: ({ children }) => <TableHeader>{children}</TableHeader>,
  tbody: ({ children }) => <TableBody>{children}</TableBody>,
  tr: ({ children }) => <TableRow className="hover:bg-muted/30">{children}</TableRow>,
  th: ({ children }) => <TableHead className="text-xs font-semibold whitespace-nowrap">{children}</TableHead>,
  td: ({ children }) => <TableCell className="text-xs whitespace-nowrap">{children}</TableCell>,
}

export function GolMessage({ message, expanded }) {
  const isUser = message.role === 'user'

  const contentEl = message.content
    ? isUser
      ? message.content
      : (
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
          {message.content}
        </ReactMarkdown>
      )
    : message.toolCall
      ? (
        <span className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin motion-reduce:animate-none" aria-hidden="true" />
          {TOOL_LABELS[message.toolCall] || `Looking up ${message.toolCall}`}{'\u2026'}
        </span>
      )
      : null

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <Avatar className="h-8 w-8 shrink-0">
        <AvatarFallback className={isUser ? 'bg-primary text-primary-foreground' : 'bg-emerald-600 text-white'}>
          {isUser ? 'U' : 'G'}
        </AvatarFallback>
      </Avatar>

      <div className={`flex-1 min-w-0 ${isUser ? 'text-right' : ''}`}>
        <div className={`inline-block rounded-lg px-3 py-2 text-sm ${
          isUser
            ? 'max-w-[85%] bg-primary text-primary-foreground'
            : 'max-w-full bg-muted text-foreground'
        }`}>
          {contentEl}
        </div>

        {message.dataCards?.length > 0 && (
          <div className="mt-2 space-y-2 text-left">
            {message.dataCards.map((card, i) => (
              <GolDataCard key={i} card={card} expanded={expanded} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
