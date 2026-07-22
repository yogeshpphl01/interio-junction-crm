/* useApi(path): GET on mount, expose { data, loading, error, reload }. */
import { useCallback, useEffect, useState } from "react";
import { api, apiError } from "@/lib/api";

export function useApi(path, { immediate = true } = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(immediate);
  const [error, setError] = useState(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get(path);
      setData(res.data);
      return res.data;
    } catch (e) {
      setError(apiError(e));
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    if (immediate) reload();
  }, [immediate, reload]);

  return { data, loading, error, reload, setData };
}
