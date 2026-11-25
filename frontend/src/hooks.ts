import { useCallback, useEffect, useState } from 'react'
import { describeError } from './api'

export function useData<T>(load: (signal: AbortSignal) => Promise<T>, interval?: number) {
  const [version, setVersion] = useState(0)
  const refresh = useCallback(() => setVersion(value => value + 1), [])
  const [data, setData] = useState<T>()
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    async function fetchData() {
      setLoading(true)
      try {
        const value = await load(controller.signal)
        if (!controller.signal.aborted) {
          setData(value)
          setError('')
        }
      } catch (error) {
        if (!controller.signal.aborted) setError(describeError(error))
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false)
          if (interval) timer = setTimeout(fetchData, interval)
        }
      }
    }
    void fetchData()
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [load, interval, version])
  return { data, error, loading, refresh }
}
