"""Central configuration: paths, expected schema and environment handling.

Configuration precedence: environment variables > .env file > defaults.
Nothing here is machine-specific; all paths derive from the repository root.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Survey years covered by the two committed cuts (see docs/design_note.md).
SURVEY_YEARS = (2014, 2016, 2018)

# Natural key of a survey observation. GSS respondent ids restart at 1 every
# survey year (verified against the NORC year files), so a respondent
# observation is only unique as (year, id).
NATURAL_KEY = ("year", "id")

# Every variable a committed extract must carry, in column order.
EXPECTED_VARIABLES = (
    "id", "year", "ballot",
    "wrkstat", "evwork", "educ", "degree", "indus10", "satjob",
    "postlife", "pray", "relig16", "news", "tvhours", "inttech",
    "relig", "attend", "reliten", "wwwhr",
    "age", "sex", "region", "wtssps",
)

# Stata tagged missing values as serialised in the extracts.
# .d don't know | .i inapplicable | .n no answer | .s skipped on web
# .r refused    | .u uncodeable   | .x not available in release
# .y not available in year        | .z see codebook
KNOWN_MISSING_TAGS = frozenset(
    {".d", ".i", ".n", ".s", ".r", ".u", ".x", ".y", ".z"}
)

EXTRACT_FILES = {
    "gss_extract_1_2014_2016": "gss_extract_1_2014_2016.json",
    "gss_extract_2_2016_2018": "gss_extract_2_2016_2018.json",
}


def _load_dotenv(path: Path) -> dict[str, str]:
    """Minimal .env parser (KEY=VALUE lines, # comments). Avoids a dependency."""
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


@dataclass(frozen=True)
class PipelineConfig:
    repo_root: Path = REPO_ROOT
    raw_dir: Path = REPO_ROOT / "source" / "data" / "raw"
    processed_dir: Path = REPO_ROOT / "source" / "data" / "processed"
    logs_dir: Path = REPO_ROOT / "logs"
    docs_dir: Path = REPO_ROOT / "docs"
    dbt_dir: Path = REPO_ROOT / "dbt"
    evidence_dir: Path = REPO_ROOT / "report" / "evidence"
    db_path: Path = REPO_ROOT / "source" / "data" / "processed" / "gss.duckdb"
    log_level: str = "INFO"
    extract_files: dict = field(default_factory=lambda: dict(EXTRACT_FILES))

    def extract_paths(self) -> dict[str, Path]:
        return {name: self.raw_dir / fname for name, fname in self.extract_files.items()}


def load_config() -> PipelineConfig:
    dotenv = _load_dotenv(REPO_ROOT / ".env")

    def setting(key: str, default: str) -> str:
        return os.environ.get(key, dotenv.get(key, default))

    db_path = Path(setting("GSS_DB_PATH", str(PipelineConfig.db_path)))
    if not db_path.is_absolute():
        db_path = REPO_ROOT / db_path
    return PipelineConfig(
        db_path=db_path,
        log_level=setting("GSS_LOG_LEVEL", "INFO").upper(),
    )
