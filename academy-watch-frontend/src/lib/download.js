// Save a Blob as a file through a temporary link (browser only; no-op elsewhere).
export function saveBlobAs(blob, filename) {
  if (typeof document === 'undefined' || typeof URL === 'undefined' || !URL.createObjectURL) return
  const objectUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objectUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(objectUrl), 0)
}
