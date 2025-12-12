"""
Study Manager - Persistent Trial Storage
=========================================
Manages optimization study persistence using SQLite.
Stores config hashes, trials, and best results for quick lookup.
"""
import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rota.models.constraints import SolverConfig
from rota.models.person import Person
from rota.solver.pairs import PairAssignment, PairSchedule
from rota.utils.logging_setup import get_logger

logger = get_logger("rota.solver.study_manager")

# Default database location
DEFAULT_DB_PATH = Path("data/studies.db")


def compute_study_hash(
    config: SolverConfig, 
    people: List[Person],
    custom_staffing: Optional[Dict] = None,
    weekend_config: Optional[Dict] = None,
) -> str:
    """
    Generate unique hash for this optimization problem.
    
    Includes: team composition, constraints, weeks, fairness mode,
              staffing requirements, weekend parameters
    Excludes: seed, time_limit, tries (vary between runs)
    
    Args:
        config: Solver configuration
        people: List of team members
        custom_staffing: Optional dict of staffing requirements (D, S, N)
        weekend_config: Optional dict of weekend configuration
        
    Returns:
        16-character hex hash
    """
    # Get config dict and remove non-deterministic fields
    config_dict = config.to_dict()
    config_dict.pop("time_limit_seconds", None)
    config_dict.pop("num_workers", None)
    config_dict.pop("workers_per_solve", None)
    config_dict.pop("parallel_portfolio", None)
    
    # Sort team by name for consistent hashing
    team_data = sorted([p.to_dict() for p in people], key=lambda x: x["name"])
    
    # Combine for hashing
    data = {
        "config": config_dict,
        "team": team_data,
    }
    
    # Include staffing if provided
    if custom_staffing:
        data["staffing"] = custom_staffing
    
    # Include weekend config if provided
    if weekend_config:
        data["weekend"] = weekend_config
    
    json_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(json_str.encode()).hexdigest()[:16]


@dataclass
class StudySummary:
    """Summary of a stored study."""
    study_hash: str
    study_name: str
    weeks: int
    team_size: int
    best_score: float
    best_seed: int
    total_trials: int
    created_at: datetime
    updated_at: datetime


@dataclass
class TrialResult:
    """Result of a single optimization trial."""
    trial_id: int
    study_hash: str
    seed: int
    score: float
    schedule_json: str
    validation_json: str
    fairness_json: str
    solve_time_seconds: float
    created_at: datetime


class StudyManager:
    """
    Manages study persistence in SQLite.
    
    Usage:
        manager = StudyManager()
        study_hash = compute_study_hash(config, people)
        
        # Check if study exists
        if manager.study_exists(study_hash):
            best = manager.get_best_trial(study_hash)
            
        # Save new trial
        manager.save_trial(study_hash, seed, score, schedule, validation, fairness)
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        """Initialize with database path."""
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Create tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS studies (
                    study_hash TEXT PRIMARY KEY,
                    study_name TEXT,
                    config_json TEXT,
                    team_json TEXT,
                    weeks INTEGER,
                    team_size INTEGER,
                    best_score REAL,
                    best_seed INTEGER,
                    total_trials INTEGER DEFAULT 0,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    study_hash TEXT REFERENCES studies(study_hash),
                    seed INTEGER,
                    score REAL,
                    schedule_json TEXT,
                    validation_json TEXT,
                    fairness_json TEXT,
                    solve_time_seconds REAL,
                    created_at TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trials_study 
                ON trials(study_hash)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trials_score 
                ON trials(study_hash, score)
            """)
            conn.commit()
        logger.debug(f"Database initialized at {self.db_path}")
    
    def study_exists(self, study_hash: str) -> bool:
        """Check if a study exists."""
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute(
                "SELECT 1 FROM studies WHERE study_hash = ?", 
                (study_hash,)
            ).fetchone()
            return result is not None
    
    def get_study_summary(self, study_hash: str) -> Optional[StudySummary]:
        """Get summary of a study."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("""
                SELECT study_hash, study_name, weeks, team_size, 
                       best_score, best_seed, total_trials, 
                       created_at, updated_at
                FROM studies WHERE study_hash = ?
            """, (study_hash,)).fetchone()
            
            if not row:
                return None
                
            return StudySummary(
                study_hash=row[0],
                study_name=row[1] or "",
                weeks=row[2],
                team_size=row[3],
                best_score=row[4],
                best_seed=row[5],
                total_trials=row[6],
                created_at=datetime.fromisoformat(row[7]) if row[7] else datetime.now(),
                updated_at=datetime.fromisoformat(row[8]) if row[8] else datetime.now(),
            )
    
    def get_study_config(self, study_hash: str) -> Optional[Dict]:
        """Get the config JSON stored with a study."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT config_json FROM studies WHERE study_hash = ?",
                (study_hash,)
            ).fetchone()
            
            if row and row[0]:
                return json.loads(row[0])
            return None
    
    def get_most_recent_config(self) -> Optional[Dict]:
        """Get config from the most recently updated study."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT config_json FROM studies ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
            
            if row and row[0]:
                return json.loads(row[0])
            return None
    
    def list_studies(self, limit: int = 20) -> List[StudySummary]:
        """List all studies, most recent first."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("""
                SELECT study_hash, study_name, weeks, team_size, 
                       best_score, best_seed, total_trials, 
                       created_at, updated_at
                FROM studies 
                ORDER BY updated_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
            
            return [
                StudySummary(
                    study_hash=row[0],
                    study_name=row[1] or "",
                    weeks=row[2],
                    team_size=row[3],
                    best_score=row[4],
                    best_seed=row[5],
                    total_trials=row[6],
                    created_at=datetime.fromisoformat(row[7]) if row[7] else datetime.now(),
                    updated_at=datetime.fromisoformat(row[8]) if row[8] else datetime.now(),
                )
                for row in rows
            ]
    
    def create_study(
        self, 
        study_hash: str, 
        config: SolverConfig, 
        people: List[Person],
        study_name: Optional[str] = None,
        custom_staffing: Optional[Dict] = None,
        weekend_config: Optional[Dict] = None,
    ):
        """Create a new study entry with full configuration context."""
        now = datetime.now().isoformat()
        
        # Serialize full configuration context
        config_dict = config.to_dict()
        if custom_staffing:
            config_dict["custom_staffing"] = custom_staffing
        if weekend_config:
            config_dict["weekend_config"] = weekend_config
            
        config_json = json.dumps(config_dict, ensure_ascii=False)
        team_json = json.dumps([p.to_dict() for p in people], ensure_ascii=False)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO studies 
                (study_hash, study_name, config_json, team_json, weeks, team_size,
                 best_score, best_seed, total_trials, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                study_hash,
                study_name or f"Study {study_hash[:8]}",
                config_json,
                team_json,
                config.weeks,
                len(people),
                float("inf"),
                0,
                0,
                now,
                now,
            ))
            conn.commit()
        logger.info(f"Created study {study_hash}")
    
    def save_trial(
        self,
        study_hash: str,
        seed: int,
        score: float,
        schedule: PairSchedule,
        validation_dict: Dict[str, Any],
        fairness_dict: Dict[str, Any],
    ):
        """Save a trial result."""
        now = datetime.now().isoformat()
        
        # Serialize schedule
        schedule_data = {
            "weeks": schedule.weeks,
            "people_count": schedule.people_count,
            "status": schedule.status,
            "score": schedule.score,
            "solve_time_seconds": schedule.solve_time_seconds,
            "stats": schedule.stats,
            "assignments": [
                {
                    "week": a.week,
                    "day": a.day,
                    "shift": a.shift,
                    "slot_idx": a.slot_idx,
                    "person_a": a.person_a,
                    "person_b": a.person_b,
                }
                for a in schedule.assignments
            ]
        }
        schedule_json = json.dumps(schedule_data, ensure_ascii=False)
        validation_json = json.dumps(validation_dict, ensure_ascii=False)
        fairness_json = json.dumps(fairness_dict, ensure_ascii=False)
        
        with sqlite3.connect(self.db_path) as conn:
            # Insert trial
            conn.execute("""
                INSERT INTO trials 
                (study_hash, seed, score, schedule_json, validation_json, 
                 fairness_json, solve_time_seconds, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                study_hash, seed, score, schedule_json, validation_json,
                fairness_json, schedule.solve_time_seconds, now,
            ))
            
            # Update study stats
            conn.execute("""
                UPDATE studies SET
                    total_trials = total_trials + 1,
                    best_score = CASE WHEN ? < best_score THEN ? ELSE best_score END,
                    best_seed = CASE WHEN ? < best_score THEN ? ELSE best_seed END,
                    updated_at = ?
                WHERE study_hash = ?
            """, (score, score, score, seed, now, study_hash))
            
            conn.commit()
        logger.debug(f"Saved trial: seed={seed}, score={score:.2f}")
    
    def get_best_trial(self, study_hash: str) -> Optional[TrialResult]:
        """Get the best trial for a study."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("""
                SELECT id, study_hash, seed, score, schedule_json, 
                       validation_json, fairness_json, solve_time_seconds, created_at
                FROM trials 
                WHERE study_hash = ?
                ORDER BY score ASC
                LIMIT 1
            """, (study_hash,)).fetchone()
            
            if not row:
                return None
                
            return TrialResult(
                trial_id=row[0],
                study_hash=row[1],
                seed=row[2],
                score=row[3],
                schedule_json=row[4],
                validation_json=row[5],
                fairness_json=row[6],
                solve_time_seconds=row[7],
                created_at=datetime.fromisoformat(row[8]) if row[8] else datetime.now(),
            )
    
    def load_schedule_from_trial(self, trial: TrialResult) -> PairSchedule:
        """Reconstruct a PairSchedule from stored trial data."""
        data = json.loads(trial.schedule_json)
        
        assignments = [
            PairAssignment(
                week=a["week"],
                day=a["day"],
                shift=a["shift"],
                slot_idx=a["slot_idx"],
                person_a=a["person_a"],
                person_b=a.get("person_b"),
            )
            for a in data["assignments"]
        ]
        
        return PairSchedule(
            assignments=assignments,
            weeks=data["weeks"],
            people_count=data["people_count"],
            status=data["status"],
            score=data["score"],
            solve_time_seconds=data["solve_time_seconds"],
            stats=data.get("stats", {}),
        )
    
    def delete_study(self, study_hash: str):
        """Delete a study and all its trials."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM trials WHERE study_hash = ?", (study_hash,))
            conn.execute("DELETE FROM studies WHERE study_hash = ?", (study_hash,))
            conn.commit()
        logger.info(f"Deleted study {study_hash}")
    
    def get_tried_seeds(self, study_hash: str) -> List[int]:
        """Get list of seeds already tried for this study."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT seed FROM trials WHERE study_hash = ?",
                (study_hash,)
            ).fetchall()
            return [row[0] for row in rows]
