import { Textarea } from './ui/textarea'
import { cn } from '@/lib/utils'

/**
 * Simple commentary editor component for creating/editing newsletter commentary.
 * Wraps a textarea with consistent styling for the admin interface.
 */
export function CommentaryEditor({ 
  value = '', 
  onChange, 
  placeholder = 'Write your commentary...',
  className,
  minRows = 4,
  ...props 
}) {
  const handleChange = (e) => {
    if (onChange) {
      onChange(e.target.value)
    }
  }

  return (
    <Textarea
      value={value}
      onChange={handleChange}
      placeholder={placeholder}
      className={cn(
        'min-h-[120px] resize-y font-normal',
        className
      )}
      rows={minRows}
      {...props}
    />
  )
}

export default CommentaryEditor
