// ============================================================
// Debounce hook — delays updating a value until the user stops
// typing for `delay` milliseconds.
// ============================================================

import { useState, useEffect } from "react";

export default function useDebounce<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}
