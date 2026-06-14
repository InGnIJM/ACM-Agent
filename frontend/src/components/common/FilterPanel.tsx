import { useState } from "react";
import {
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Typography,
  FormGroup,
  FormControlLabel,
  Checkbox,
  Slider,
  Autocomplete,
  TextField,
  Button,
  Box,
  Chip,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import FilterListIcon from "@mui/icons-material/FilterList";

// ============================================================
// Types
// ============================================================

export interface FilterPanelOption {
  value: string;
  label: string;
}

export interface FilterPanelProps {
  platforms: FilterPanelOption[];
  selectedPlatforms: string[];
  onPlatformsChange: (platforms: string[]) => void;

  difficultyRange: [number, number];
  onDifficultyRangeChange: (range: [number, number]) => void;

  tags: FilterPanelOption[];
  selectedTags: string[];
  onTagsChange: (tags: string[]) => void;

  onReset?: () => void;
  defaultExpanded?: boolean;
}

// ============================================================
// Component
// ============================================================

function FilterPanel({
  platforms,
  selectedPlatforms,
  onPlatformsChange,
  difficultyRange,
  onDifficultyRangeChange,
  tags,
  selectedTags,
  onTagsChange,
  onReset,
  defaultExpanded = false,
}: FilterPanelProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  const handlePlatformToggle = (value: string) => {
    if (selectedPlatforms.includes(value)) {
      onPlatformsChange(selectedPlatforms.filter((p) => p !== value));
    } else {
      onPlatformsChange([...selectedPlatforms, value]);
    }
  };

  const handleDifficultyChange = (_event: Event, newValue: number | number[]) => {
    onDifficultyRangeChange(newValue as [number, number]);
  };

  const handleReset = () => {
    onReset?.();
  };

  const hasActiveFilters =
    selectedPlatforms.length > 0 ||
    selectedTags.length > 0 ||
    difficultyRange[0] > 1 ||
    difficultyRange[1] < 10;

  return (
    <Accordion
      expanded={expanded}
      onChange={(_e, isExpanded) => setExpanded(isExpanded)}
      sx={{ mb: 2 }}
      variant="outlined"
    >
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Box display="flex" alignItems="center" gap={1} width="100%">
          <FilterListIcon color="action" />
          <Typography fontWeight={600}>Filters</Typography>
          {hasActiveFilters && (
            <Chip
              label={
                selectedPlatforms.length +
                selectedTags.length +
                (difficultyRange[0] > 1 || difficultyRange[1] < 10 ? 1 : 0)
              }
              size="small"
              color="primary"
              variant="outlined"
            />
          )}
        </Box>
      </AccordionSummary>

      <AccordionDetails>
        {/* Platform checkboxes */}
        <Box mb={3}>
          <Typography variant="subtitle2" gutterBottom fontWeight={600}>
            Platform
          </Typography>
          <FormGroup row>
            {platforms.map((p) => (
              <FormControlLabel
                key={p.value}
                control={
                  <Checkbox
                    checked={selectedPlatforms.includes(p.value)}
                    onChange={() => handlePlatformToggle(p.value)}
                    size="small"
                  />
                }
                label={p.label}
              />
            ))}
          </FormGroup>
        </Box>

        {/* Difficulty range slider */}
        <Box mb={3}>
          <Typography variant="subtitle2" gutterBottom fontWeight={600}>
            Difficulty: {difficultyRange[0]} - {difficultyRange[1]}
          </Typography>
          <Box px={1}>
            <Slider
              value={difficultyRange}
              onChange={handleDifficultyChange}
              min={1}
              max={10}
              step={1}
              marks={[
                { value: 1, label: "1" },
                { value: 5, label: "5" },
                { value: 10, label: "10" },
              ]}
              valueLabelDisplay="auto"
              size="small"
            />
          </Box>
        </Box>

        {/* Tag multi-select */}
        <Box mb={2}>
          <Typography variant="subtitle2" gutterBottom fontWeight={600}>
            Tags
          </Typography>
          <Autocomplete
            multiple
            size="small"
            options={tags}
            value={tags.filter((t) => selectedTags.includes(t.value))}
            onChange={(_event, newValue) =>
              onTagsChange(newValue.map((v) => v.value))
            }
            getOptionLabel={(option) => option.label}
            renderInput={(params) => (
              <TextField {...params} placeholder="Select tags..." />
            )}
            renderTags={(tagValue, getTagProps) =>
              tagValue.map((option, index) => {
                const { key, ...rest } = getTagProps({ index });
                return (
                  <Chip
                    key={key}
                    label={option.label}
                    size="small"
                    {...rest}
                  />
                );
              })
            }
          />
        </Box>

        {/* Reset button */}
        {onReset && (
          <Box display="flex" justifyContent="flex-end">
            <Button
              size="small"
              onClick={handleReset}
              disabled={!hasActiveFilters}
            >
              Reset Filters
            </Button>
          </Box>
        )}
      </AccordionDetails>
    </Accordion>
  );
}

export default FilterPanel;
