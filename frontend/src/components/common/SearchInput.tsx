import { useState, useEffect } from "react";
import { TextField, InputAdornment } from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import ClearIcon from "@mui/icons-material/Clear";
import IconButton from "@mui/material/IconButton";

// ============================================================
// useDebounce hook
// ============================================================

export function useDebounce<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState<T>(value);

  useEffect(() => {
    if (delayMs <= 0) {
      setDebounced(value);
      return;
    }
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}

// ============================================================
// Types
// ============================================================

export interface SearchInputProps {
  value?: string;
  placeholder?: string;
  debounceMs?: number;
  onSearch: (query: string) => void;
  fullWidth?: boolean;
  size?: "small" | "medium";
  disabled?: boolean;
  autoFocus?: boolean;
  clearable?: boolean;
}

// ============================================================
// Component
// ============================================================

function SearchInput({
  value: externalValue,
  placeholder = "Search...",
  debounceMs = 300,
  onSearch,
  fullWidth = true,
  size = "small",
  disabled = false,
  autoFocus = false,
  clearable = true,
}: SearchInputProps) {
  const [internalValue, setInternalValue] = useState<string>(
    externalValue ?? ""
  );
  const debouncedValue = useDebounce(internalValue, debounceMs);

  const isControlled = externalValue !== undefined;
  const displayValue = isControlled ? externalValue : internalValue;

  // Fire onSearch when debounced value changes
  useEffect(() => {
    onSearch(debouncedValue);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedValue]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const next = e.target.value;
    if (!isControlled) {
      setInternalValue(next);
    }
    // If debounce is 0, fire immediately for controlled mode too
    if (isControlled && debounceMs <= 0) {
      onSearch(next);
    }
    // For controlled + debounced, fire via the debounced effect on externalValue
    if (isControlled && debounceMs > 0) {
      onSearch(next);
    }
  };

  const handleClear = () => {
    if (!isControlled) {
      setInternalValue("");
    }
    onSearch("");
  };

  return (
    <TextField
      value={displayValue}
      onChange={handleChange}
      placeholder={placeholder}
      fullWidth={fullWidth}
      size={size}
      disabled={disabled}
      autoFocus={autoFocus}
      variant="outlined"
      InputProps={{
        startAdornment: (
          <InputAdornment position="start">
            <SearchIcon color="action" />
          </InputAdornment>
        ),
        endAdornment:
          clearable && displayValue.length > 0 ? (
            <InputAdornment position="end">
              <IconButton size="small" onClick={handleClear} edge="end" aria-label="Clear search">
                <ClearIcon fontSize="small" />
              </IconButton>
            </InputAdornment>
          ) : undefined,
      }}
      sx={{
        "& .MuiOutlinedInput-root": {
          borderRadius: 2,
        },
      }}
    />
  );
}

export default SearchInput;
