"""Tag and difficulty normalization for ACM problem platforms."""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Union


class TagNormalizer:
    """Normalize platform-specific tags to a unified taxonomy."""

    def __init__(self, taxonomy_path: Optional[str] = None):
        if taxonomy_path is None:
            taxonomy_path = Path(__file__).parent / "taxonomy.json"
        with open(taxonomy_path, "r", encoding="utf-8") as f:
            self._taxonomy = json.load(f)
        self._reverse_index: Dict[str, Dict[str, str]] = {}
        self._all_tags: List[str] = []
        self._build_reverse_index()

    def _build_reverse_index(self):
        """Build reverse index: {platform: {raw_tag: normalized_tag}}."""
        self._reverse_index = {}
        self._all_tags = []
        seen_tags = set()

        categories = self._taxonomy.get("categories", {})
        for _cat_name, cat_data in categories.items():
            subcategories = cat_data.get("subcategories", {})
            for _sub_name, sub_data in subcategories.items():
                for topic in sub_data.get("topics", []):
                    if topic not in seen_tags:
                        seen_tags.add(topic)
                        self._all_tags.append(topic)

                aliases = sub_data.get("aliases", {})
                for platform, mapping in aliases.items():
                    if platform not in self._reverse_index:
                        self._reverse_index[platform] = {}
                    for raw_tag, normalized_tag in mapping.items():
                        self._reverse_index[platform][raw_tag] = normalized_tag

    def normalize_tags(self, platform: str, raw_tags: List[str]) -> List[str]:
        """Normalize a list of raw tags for a given platform.

        Unmapped tags are returned as "unmapped:raw_tag".
        """
        index = self._reverse_index.get(platform, {})

        normalized = []
        for tag in raw_tags:
            if tag in index:
                normalized.append(index[tag])
            else:
                normalized.append(f"unmapped:{tag}")
        return normalized

    def get_all_tags(self) -> List[str]:
        """Return a flat list of all normalized tags."""
        return list(self._all_tags)


class DifficultyNormalizer:
    """Normalize platform-specific difficulty ratings to a 1-10 float scale."""

    _LUOGU_MAP: Dict[str, float] = {
        "入门": 1,
        "普及-": 2,
        "普及/提高-": 3,
        "普及+/提高": 4,
        "提高+/省选-": 5,
        "省选/NOI-": 6,
        "NOI/NOI+": 7,
        "NOI+": 8,
        "CTSC": 9,
        "CTSC+": 10,
    }

    _LEETCODE_MAP: Dict[str, float] = {
        "Easy": 3,
        "Medium": 5,
        "Hard": 8,
    }

    @staticmethod
    def _codeforces(rating: Union[int, float]) -> float:
        return max(1.0, min(10.0, (rating - 800) / 300 + 1))

    @staticmethod
    def _atcoder(rating: Union[int, float]) -> float:
        return max(1.0, min(10.0, (rating - 100) / 300 + 1))

    @staticmethod
    def _nowcoder(difficulty: Union[int, float]) -> float:
        return max(1.0, min(10.0, difficulty / 5))

    def normalize(self, platform: str, raw_difficulty: Union[str, int, float]) -> float:
        """Normalize a difficulty value to a float in [1, 10].

        Returns 5.0 for unknown platforms.
        """
        platform_lower = platform.lower()

        if platform_lower == "luogu":
            if isinstance(raw_difficulty, str) and raw_difficulty in self._LUOGU_MAP:
                return self._LUOGU_MAP[raw_difficulty]
            return 5.0

        if platform_lower == "leetcode":
            if isinstance(raw_difficulty, str) and raw_difficulty in self._LEETCODE_MAP:
                return self._LEETCODE_MAP[raw_difficulty]
            return 5.0

        if platform_lower == "codeforces":
            try:
                return self._codeforces(float(raw_difficulty))
            except (ValueError, TypeError):
                return 5.0

        if platform_lower == "atcoder":
            try:
                return self._atcoder(float(raw_difficulty))
            except (ValueError, TypeError):
                return 5.0

        if platform_lower == "nowcoder":
            try:
                return self._nowcoder(float(raw_difficulty))
            except (ValueError, TypeError):
                return 5.0

        return 5.0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--update-taxonomy":
        normalizer = TagNormalizer()
        print(f"Reverse index rebuilt: {len(normalizer._reverse_index)} platforms")
        print(f"Total normalized tags: {len(normalizer._all_tags)}")
    else:
        print("Usage: python normalizer.py --update-taxonomy")
