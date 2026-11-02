"""Pipeline orchestrator (CLI).

Runs the end-to-end workflow as ordered, fail-fast stages:

    check-env -> validate -> profile -> init-db -> ingest
    -> dbt-seed -> dbt-source-test -> dbt-run -> dbt-test
    -> analyses -> dbt-docs -> summary

Usage (from /source):
    python -m pipeline.main all            # full pipeline
    python -m pipeline.main validate       # single stage
    python -m pipeline.main ingest --force # reload even if files are unchanged

A failed critical stage stops the run: downstream stages never execute on top
of failed validation, ingestion or tests. Every run writes a log file and a
JSON run summary under /logs.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from .config import PipelineConfig, load_config
from .database import DatabaseError, GssDatabase
from .extract_loader import ExtractFormatError, load_extract
from .logging_config import new_run_id, setup_logging
from .profiling import profile_extracts, write_profile
from .validation import validate_extract, write_quarantine

logger = logging.getLogger("pipeline")


class StageFailure(Exception):
    """A stage failed; downstream stages must not run."""


class PipelineRunner:
    def __init__(self, config: PipelineConfig, run_id: str, force: bool = False):
        self.config = config
        self.run_id = run_id
        self.force = force
        self.extracts = []          # list[ExtractFile]
        self.validations = {}       # name -> ValidationResult
        self.load_stats = []        # list[LoadStats]
        self.stage_results = []     # list[dict]

    # -- stages ---------------------------------------------------------------

    def stage_check_env(self) -> str:
        if sys.version_info < (3, 11):
            raise StageFailure(f"Python >= 3.11 required, found {sys.version.split()[0]}")
        missing = [
            str(p) for p in self.config.extract_paths().values() if not p.exists()
        ]
        if missing:
            raise StageFailure(f"committed extracts not found: {missing}")
        if shutil.which("dbt") is None:
            raise StageFailure("dbt executable not found on PATH (pip install -r source/requirements.txt)")
        profiles = self.config.dbt_dir / "profiles.yml"
        if not profiles.exists():
            example = self.config.dbt_dir / "profiles.yml.example"
            shutil.copyfile(example, profiles)
            logger.info("created dbt/profiles.yml from profiles.yml.example")
        return f"python {sys.version.split()[0]}, dbt found, {len(self.config.extract_files)} extracts present"

    def stage_validate(self) -> str:
        self.extracts = []
        self.validations = {}
        for name, path in self.config.extract_paths().items():
            try:
                extract = load_extract(name, path)
            except ExtractFormatError as exc:
                raise StageFailure(str(exc)) from exc
            result = validate_extract(extract)
            write_quarantine(result, self.config.processed_dir)
            self.extracts.append(extract)
            self.validations[name] = result
            if not result.ok:
                raise StageFailure(
                    f"{name}: {result.quarantined_count} malformed records quarantined "
                    f"(see {self.config.processed_dir}); refusing to load a corrupt extract"
                )
        total = sum(v.valid_count for v in self.validations.values())
        return f"{total:,} records valid across {len(self.extracts)} extracts, 0 quarantined"

    def stage_profile(self) -> str:
        profile = profile_extracts(self.extracts)
        path = write_profile(
            profile, self.extracts, self.config.docs_dir, self.config.evidence_dir
        )
        cross = profile["cross_extract"]
        return (
            f"profile written to {path.name}; distinct observations "
            f"{cross['distinct_respondents_overall']:,}, overlap {cross['overlap_respondents']:,}"
        )

    def stage_init_db(self) -> str:
        db = GssDatabase(self.config.db_path)
        try:
            db.init_schema()
        finally:
            db.close()
        return f"schema ready at {self.config.db_path}"

    def stage_ingest(self) -> str:
        db = GssDatabase(self.config.db_path)
        try:
            self.load_stats = []
            for extract in self.extracts:
                stats = db.load_extract(
                    extract, self.validations[extract.name], self.run_id, self.force
                )
                self.load_stats.append(stats)
        except DatabaseError as exc:
            raise StageFailure(str(exc)) from exc
        finally:
            db.close()
        return "; ".join(
            f"{s.extract_name}: {s.status} ({s.records_inserted} inserted)"
            for s in self.load_stats
        )

    def stage_dbt_seed(self) -> str:
        return self._dbt("seed")

    def stage_dbt_source_test(self) -> str:
        return self._dbt("test", "--select", "source:*")

    def stage_dbt_run(self) -> str:
        return self._dbt("run")

    def stage_dbt_test(self) -> str:
        return self._dbt("test")

    def stage_analyses(self) -> str:
        self._dbt("compile")
        compiled_dir = (
            self.config.dbt_dir / "target" / "compiled" / "gss_pipeline" / "analyses"
        )
        sql_files = sorted(compiled_dir.glob("*.sql"))
        if not sql_files:
            raise StageFailure(f"no compiled analyses found under {compiled_dir}")
        out_dir = self.config.evidence_dir / "analysis_results"
        out_dir.mkdir(parents=True, exist_ok=True)
        conn = duckdb.connect(str(self.config.db_path), read_only=True)
        try:
            for sql_path in sql_files:
                cursor = conn.execute(sql_path.read_text(encoding="utf-8"))
                columns = [d[0] for d in cursor.description]
                rows = cursor.fetchall()
                csv_path = out_dir / f"{sql_path.stem}.csv"
                with open(csv_path, "w", newline="", encoding="utf-8") as fh:
                    writer = csv.writer(fh)
                    writer.writerow(columns)
                    writer.writerows(rows)
                logger.info("analysis %s: %d rows -> %s", sql_path.stem, len(rows), csv_path.name)
        finally:
            conn.close()
        return f"{len(sql_files)} analytical queries executed; results in {out_dir}"

    def stage_dbt_docs(self) -> str:
        return self._dbt("docs", "generate")

    # -- helpers ---------------------------------------------------------------

    def _dbt(self, *args: str) -> str:
        cmd = [
            shutil.which("dbt"), *args,
            "--project-dir", str(self.config.dbt_dir),
            "--profiles-dir", str(self.config.dbt_dir),
        ]
        logger.info("running: dbt %s", " ".join(args))
        proc = subprocess.run(
            cmd, cwd=self.config.repo_root, capture_output=True, text=True
        )
        for line in (proc.stdout or "").splitlines():
            logger.info("dbt | %s", line)
        if proc.returncode != 0:
            for line in (proc.stderr or "").splitlines():
                logger.error("dbt | %s", line)
            raise StageFailure(f"dbt {' '.join(args)} failed (exit {proc.returncode})")
        return f"dbt {' '.join(args)} succeeded"

    # -- driver ----------------------------------------------------------------

    STAGES = (
        ("check-env", stage_check_env),
        ("validate", stage_validate),
        ("profile", stage_profile),
        ("init-db", stage_init_db),
        ("ingest", stage_ingest),
        ("dbt-seed", stage_dbt_seed),
        ("dbt-source-test", stage_dbt_source_test),
        ("dbt-run", stage_dbt_run),
        ("dbt-test", stage_dbt_test),
        ("analyses", stage_analyses),
        ("dbt-docs", stage_dbt_docs),
    )

    def run(self, selected: list[str]) -> bool:
        stages = [(n, fn) for n, fn in self.STAGES if "all" in selected or n in selected]
        # stages that need extracts in memory but are being run standalone
        needs_validate = {"profile", "ingest"}
        if "all" not in selected and not self.extracts:
            if needs_validate & set(selected) and "validate" not in selected:
                stages.insert(0, ("validate", PipelineRunner.stage_validate))

        ok = True
        for name, fn in stages:
            start = time.perf_counter()
            try:
                detail = fn(self)
                status = "ok"
            except StageFailure as exc:
                detail, status, ok = str(exc), "failed", False
            duration = round(time.perf_counter() - start, 2)
            self.stage_results.append(
                {"stage": name, "status": status, "duration_s": duration, "detail": detail}
            )
            log = logger.info if status == "ok" else logger.error
            log("stage %-16s %-7s (%.2fs) %s", name, status.upper(), duration, detail)
            if not ok:
                logger.error("aborting: downstream stages skipped after %s failed", name)
                break
        self._write_summary(ok)
        return ok

    def _write_summary(self, ok: bool) -> None:
        summary = {
            "run_id": self.run_id,
            "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": "success" if ok else "failed",
            "force": self.force,
            "extracts": {
                name: {
                    "records_in_file": v.total_records,
                    "valid": v.valid_count,
                    "quarantined": v.quarantined_count,
                    "duplicate_keys_in_file": v.duplicate_keys,
                }
                for name, v in self.validations.items()
            },
            "loads": [vars(s) for s in self.load_stats],
            "stages": self.stage_results,
        }
        self.config.logs_dir.mkdir(parents=True, exist_ok=True)
        path = self.config.logs_dir / f"summary_{self.run_id}.json"
        path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        logger.info("run summary written to %s", path)


def main(argv: list[str] | None = None) -> int:
    stage_names = [name for name, _ in PipelineRunner.STAGES]
    parser = argparse.ArgumentParser(
        prog="python -m pipeline.main",
        description="GSS extract ingestion and transformation pipeline",
    )
    parser.add_argument(
        "stages", nargs="+", choices=["all", *stage_names],
        help="stages to run, in pipeline order ('all' for the full workflow)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="reload extracts even when their content is unchanged",
    )
    args = parser.parse_args(argv)

    config = load_config()
    run_id = new_run_id()
    log_path = setup_logging(config.logs_dir, run_id, config.log_level)
    logger.info("run %s starting; stages=%s force=%s", run_id, args.stages, args.force)
    logger.info("log file: %s", log_path)

    runner = PipelineRunner(config, run_id, force=args.force)
    ok = runner.run(args.stages)
    logger.info("run %s %s", run_id, "succeeded" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
