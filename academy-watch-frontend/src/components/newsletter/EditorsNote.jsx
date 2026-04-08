/**
 * Editor's note / week summary block. Italic editorial prose with a primary
 * accent border, capped at 70ch reading width for editorial pacing.
 *
 * If `summary` is empty, renders nothing.
 */
export function EditorsNote({ summary }) {
  if (!summary) return null

  return (
    <section className="mb-10 sm:mb-12">
      <div className="border-l-2 border-[var(--tl-primary)]/40 pl-5 sm:pl-6 max-w-[70ch]">
        <p className="text-[15px] sm:text-base md:text-lg leading-[1.7] text-[var(--tl-text-body)] italic m-0">
          {summary}
        </p>
      </div>
    </section>
  )
}

export default EditorsNote
