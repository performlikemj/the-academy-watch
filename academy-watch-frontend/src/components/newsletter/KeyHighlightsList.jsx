/**
 * Key highlights list — numbered editorial bullet points. Replaces the old
 * amber-themed React block with the Tactical Lens treatment.
 */
export function KeyHighlightsList({ highlights }) {
  if (!highlights || !Array.isArray(highlights) || highlights.length === 0) return null

  return (
    <section className="mb-10 sm:mb-12">
      <h2 className="tl-eyebrow m-0 mb-4">Key Highlights</h2>
      <ul className="list-none p-0 m-0 space-y-3">
        {highlights.map((highlight, idx) => (
          <li key={idx} className="flex items-start gap-3">
            <span
              className="flex-shrink-0 mt-0.5 inline-flex items-center justify-center h-6 w-6 rounded-full text-[11px] font-bold"
              style={{
                background: 'var(--tl-primary-soft)',
                color: 'var(--tl-primary)',
              }}
            >
              {idx + 1}
            </span>
            <span className="text-[14px] sm:text-[15px] leading-relaxed text-[var(--tl-text-body)]">
              {highlight}
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default KeyHighlightsList
