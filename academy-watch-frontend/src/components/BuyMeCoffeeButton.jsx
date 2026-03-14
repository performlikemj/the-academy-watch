import { useEffect, useRef } from 'react'
import { BMC_SCRIPT_SRC, BUTTON_DATASET, createBuyMeCoffeeScriptConfig } from './bmcButtonConfig.js'

export { createBuyMeCoffeeScriptConfig }

const FALLBACK_HTML = `
  <a
    href="https://www.buymeacoffee.com/${BUTTON_DATASET.slug}"
    target="_blank"
    rel="noopener noreferrer"
    style="
      display:inline-flex;
      align-items:center;
      gap:8px;
      padding:10px 16px;
      border-radius:9999px;
      background:${BUTTON_DATASET.color};
      color:${BUTTON_DATASET.fontColor};
      font-family:'${BUTTON_DATASET.font}', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      font-size:16px;
      font-weight:600;
      text-decoration:none;
      box-shadow:0 10px 20px rgba(0,0,0,0.12);
    "
  >
    ☕
    <span>${BUTTON_DATASET.text}</span>
  </a>
`

let scriptPromise

function loadBmcScript() {
  if (typeof window === 'undefined') return Promise.resolve()
  if (window.bmcBtnWidget) return Promise.resolve()

  if (!scriptPromise) {
    scriptPromise = new Promise((resolve, reject) => {
      const head = document.head || document.getElementsByTagName('head')[0]
      if (!head) {
        reject(new Error('Missing <head> element'))
        return
      }

      // Avoid double-inserting the script tag
      if (document.querySelector(`script[src="${BMC_SCRIPT_SRC}"]`)) {
        resolve()
        return
      }

      const script = document.createElement('script')
      script.type = 'text/javascript'
      script.src = BMC_SCRIPT_SRC
      script.async = true
      script.onload = () => resolve()
      script.onerror = () => reject(new Error('Failed to load Buy Me a Coffee widget'))
      head.appendChild(script)
    })
  }

  return scriptPromise
}

function renderButton(target) {
  if (!target || typeof window === 'undefined' || typeof window.bmcBtnWidget !== 'function') {
    target.innerHTML = FALLBACK_HTML
    return
  }

  try {
    const html = window.bmcBtnWidget(
      BUTTON_DATASET.text,
      BUTTON_DATASET.slug,
      BUTTON_DATASET.color,
      BUTTON_DATASET.emoji,
      BUTTON_DATASET.font,
      BUTTON_DATASET.fontColor,
      BUTTON_DATASET.outlineColor,
      BUTTON_DATASET.coffeeColor,
    )
    target.innerHTML = html || FALLBACK_HTML
  } catch (error) {
    console.warn('BuyMeCoffeeButton render failed, falling back to static link.', error)
    target.innerHTML = FALLBACK_HTML
  }
}

export function BuyMeCoffeeButton({ align = 'center', className = '' }) {
  const containerRef = useRef(null)

  useEffect(() => {
    const node = containerRef.current
    if (!node) return undefined

    let cancelled = false

    node.innerHTML = FALLBACK_HTML

    const applyWidget = () => {
      if (cancelled) return
      renderButton(node)
    }

    if (typeof window !== 'undefined' && typeof window.bmcBtnWidget === 'function') {
      applyWidget()
    } else {
      loadBmcScript()
        .then(applyWidget)
        .catch(() => {
          // Fallback already rendered; nothing else to do
        })
    }

    return () => {
      cancelled = true
      node.innerHTML = ''
    }
  }, [])

  const alignment = align === 'left'
    ? 'justify-start'
    : align === 'right'
      ? 'justify-end'
      : 'justify-center'

  return (
    <div className={`my-6 flex ${alignment} ${className}`.trim()}>
      <div ref={containerRef} aria-label="Support The Academy Watch" />
    </div>
  )
}
