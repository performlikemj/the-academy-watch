import { useId, useMemo, useRef, useState } from 'react'
import * as Popover from '@radix-ui/react-popover'
import { Check, ChevronsUpDown } from 'lucide-react'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { canonicalTimezone } from '@/lib/opportunity-time'
import { timezoneGroups, timezoneSearch } from '@/lib/opportunity-timezone-options'
import './opportunity-timezone-picker.css'

export function OpportunityTimezonePicker({ value, onChange, disabled = false }) {
  const [open, setOpen] = useState(false)
  const [now, setNow] = useState(() => new Date())
  const id = useId()
  const commandRef = useRef(null)
  const triggerRef = useRef(null)
  // Reuse current offsets for a minute; refresh on opening after that. Advertised date conversion still uses its own instant.
  const groups = useMemo(() => timezoneGroups(now), [now])
  const zone = canonicalTimezone(value)
  const selected = groups.flatMap(group => group.options).find(option => option.zone === zone)
  return <div className="opp-field">
    <label id={`${id}-label`} htmlFor={`${id}-trigger`}>Time zone</label>
    <Popover.Root open={open && !disabled} onOpenChange={next => {
      if (next) {
        // Make room above the field on short viewports, including a software keyboard.
        if ((window.visualViewport?.height ?? window.innerHeight) < 500) triggerRef.current?.scrollIntoView({ block: 'end' })
        setNow(new Date())
      }
      setOpen(next)
    }}>
      <Popover.Trigger asChild>
        <button ref={triggerRef} id={`${id}-trigger`} type="button" role="combobox" aria-labelledby={`${id}-label`} aria-describedby={`${id}-value`} aria-expanded={open && !disabled} disabled={disabled} className="opp-timezone-trigger">
          <span id={`${id}-value`}><span>{selected?.label ?? zone}</span><span className="opp-timezone-zone">{zone}</span></span>
          <ChevronsUpDown size={16} aria-hidden="true" />
        </button>
      </Popover.Trigger>
      {/* Stay inside the native modal dialog's top layer and focus scope. */}
      <Popover.Content className="opp-timezone-popover" align="start" side="top" sideOffset={6} collisionPadding={16} aria-label="Choose time zone" onOpenAutoFocus={() => {
        // cmdk's initial scroll can run before Radix finishes placing the popover.
        requestAnimationFrame(() => commandRef.current?.querySelector('[cmdk-item][data-selected="true"]')?.scrollIntoView({ block: 'nearest' }))
      }}>
        <Command ref={commandRef} defaultValue={zone} filter={timezoneSearch}>
          <CommandInput placeholder="Search city or time zone…" aria-label="Search time zones" />
          <CommandList label="Time zones">
            <CommandEmpty>No time zones found.</CommandEmpty>
            {groups.map(group => <CommandGroup key={group.region} heading={group.region}>
              {group.options.map(option => <CommandItem key={option.zone} value={option.zone} keywords={option.keywords} onSelect={() => { onChange(option.zone); setOpen(false) }}>
                <span><span>{option.label}</span><span className="opp-timezone-zone">{option.zone}</span></span>
                {option.zone === zone && <Check size={16} aria-hidden="true" />}
              </CommandItem>)}
            </CommandGroup>)}
          </CommandList>
        </Command>
      </Popover.Content>
    </Popover.Root>
  </div>
}
