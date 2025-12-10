"""CSV loading and saving for team data."""
from pathlib import Path
from typing import List, Union

import pandas as pd

from rota.models.person import Person


def _safe_int(value, default: int = 0) -> int:
    """Safely convert value to int."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _safe_bool(value, default: bool = False) -> bool:
    """Safely convert value to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "oui")
    return default


def load_team(source: Union[str, Path, pd.DataFrame]) -> List[Person]:
    """
    Load team from CSV file or DataFrame.
    
    Args:
        source: Path to CSV file or pandas DataFrame
        
    Returns:
        List of Person objects
    """
    if isinstance(source, pd.DataFrame):
        df = source.copy()
    else:
        df = pd.read_csv(source)
    
    df = df.fillna("")
    
    # Required column
    if "name" not in df.columns:
        raise ValueError("CSV must have a 'name' column")
    
    people = []
    for idx, row in df.iterrows():
        name = str(row["name"]).strip()
        if not name:
            continue
        
        # Parse EDO fixed day
        edo_fixed = str(row.get("edo_fixed_day", "")).strip()
        if edo_fixed and edo_fixed not in ("Lun", "Mar", "Mer", "Jeu", "Ven"):
            edo_fixed = None
        
        person = Person(
            name=name,
            workdays_per_week=_safe_int(row.get("workdays_per_week"), 5),
            weeks_pattern=max(1, _safe_int(row.get("weeks_pattern"), 1)),
            prefers_night=_safe_bool(row.get("prefers_night")),
            no_evening=_safe_bool(row.get("no_evening")),
            max_nights=_safe_int(row.get("max_nights"), 99),
            edo_eligible=_safe_bool(row.get("edo_eligible")),
            edo_fixed_day=edo_fixed or None,
            team=str(row.get("team", "")).strip(),
            available_weekends=_safe_bool(row.get("available_weekends", True)),
            max_weekends_per_month=_safe_int(row.get("max_weekends_per_month"), 2),
            id=idx,
        )
        people.append(person)
    
    # Assign sequential IDs if needed
    for i, p in enumerate(people):
        p.id = i
    
    return people


def save_team(people: List[Person], path: Union[str, Path]) -> None:
    """
    Save team to CSV file.
    
    Args:
        people: List of Person objects
        path: Output path
    """
    if not people:
        df = pd.DataFrame(columns=[
            "name", "workdays_per_week", "weeks_pattern", "prefers_night",
            "no_evening", "max_nights", "edo_eligible", "edo_fixed_day", "team",
            "available_weekends", "max_weekends_per_month"
        ])
    else:
        rows = [p.to_dict() for p in people]
        df = pd.DataFrame(rows)
    
    # Convert bools to 1/0 for CSV
    for col in ["prefers_night", "no_evening", "edo_eligible", "available_weekends"]:
        if col in df.columns:
            df[col] = df[col].astype(int)
    
    df.to_csv(path, index=False)


def team_to_dataframe(people: List[Person]) -> pd.DataFrame:
    """Convert team list to DataFrame for display."""
    if not people:
        return pd.DataFrame()
    return pd.DataFrame([p.to_dict() for p in people])
