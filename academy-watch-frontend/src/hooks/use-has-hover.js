import * as React from "react"

export function useHasHover() {
  const [hasHover, setHasHover] = React.useState(undefined)

  React.useEffect(() => {
    const mql = window.matchMedia("(pointer: fine)")
    const onChange = () => {
      setHasHover(mql.matches)
    }
    mql.addEventListener("change", onChange)
    setHasHover(mql.matches)
    return () => mql.removeEventListener("change", onChange)
  }, [])

  return !!hasHover
}
