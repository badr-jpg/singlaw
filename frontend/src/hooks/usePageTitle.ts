import { useEffect } from 'react'

/** Sets the document title for the current route. */
export function usePageTitle(title: string) {
  useEffect(() => {
    document.title = title
  }, [title])
}
