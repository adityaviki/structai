import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiClientError } from './client'

interface AsyncState<T> {
  data: T | null
  loading: boolean
  error: Error | null
}

export function useAsync<T>(fetcher: () => Promise<T>, deps: React.DependencyList): AsyncState<T> & { reload: () => void } {
  const [state, setState] = useState<AsyncState<T>>({ data: null, loading: true, error: null })
  const aliveRef = useRef(true)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const memoFetcher = useCallback(fetcher, deps)

  const run = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }))
    try {
      const data = await memoFetcher()
      if (aliveRef.current) setState({ data, loading: false, error: null })
    } catch (err) {
      if (aliveRef.current)
        setState({ data: null, loading: false, error: err as Error })
    }
  }, [memoFetcher])

  useEffect(() => {
    aliveRef.current = true
    void run()
    return () => {
      aliveRef.current = false
    }
  }, [run])

  return { ...state, reload: run }
}

export function isNotFound(err: Error | null): boolean {
  return !!err && err instanceof ApiClientError && err.status === 404
}
