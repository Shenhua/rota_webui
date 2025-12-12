"""
Session State Management
========================
Encapsulates all Streamlit session state interactions.
"""
from typing import Optional, List, Dict, Any, TYPE_CHECKING
import streamlit as st

if TYPE_CHECKING:
    from rota.solver.pairs import PairSchedule
    from rota.solver.edo import EDOPlan
    from rota.solver.staffing import WeekStaffing
    from rota.solver.validation import ScheduleValidation, FairnessMetrics

class SessionStateManager:
    """Manages type-safe access to session state."""
    
    @staticmethod
    def init_state():
        """Initialize default session state values."""
        defaults: Dict[str, Any] = {
            "people": [],
            "schedule": None,
            "w_result": None,
            "validation": None,
            "fairness": None,
            "best_seed": None,
            "best_score": None,
            "edo_plan": None,
            "staffing": None,
            "study_hash": None,
            "trigger_optimize": False,
            # Config defaults
            "config_weeks": 4,
            "config_tries": 5,
            "config_seed": 0,
            "merge_calendars": False,
        }
        
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value

    @property
    def schedule(self) -> Optional['PairSchedule']:
        return st.session_state.get("schedule")
    
    @schedule.setter
    def schedule(self, value: 'PairSchedule'):
        st.session_state["schedule"] = value
        
    @property
    def validation(self) -> Optional['ScheduleValidation']:
        return st.session_state.get("validation")
        
    @validation.setter
    def validation(self, value: 'ScheduleValidation'):
        st.session_state["validation"] = value
        
    @property
    def fairness(self) -> Optional['FairnessMetrics']:
        return st.session_state.get("fairness")
        
    @fairness.setter
    def fairness(self, value: 'FairnessMetrics'):
        st.session_state["fairness"] = value

    @property
    def people(self) -> List[Any]:
        p = st.session_state.get("people", [])
        return p if isinstance(p, list) else []
        
    @property
    def edo_plan(self) -> Optional['EDOPlan']:
        return st.session_state.get("edo_plan")

    @edo_plan.setter
    def edo_plan(self, value: 'EDOPlan'):
        st.session_state["edo_plan"] = value

    @property
    def staffing(self) -> Optional['WeekStaffing']:
        return st.session_state.get("staffing")

    @staffing.setter
    def staffing(self, value: 'WeekStaffing'):
        st.session_state["staffing"] = value

    @property
    def w_result(self) -> Optional[Any]:
        return st.session_state.get("w_result")

    @w_result.setter
    def w_result(self, value: Any):
        st.session_state["w_result"] = value

    @property
    def best_seed(self) -> Optional[int]:
        return st.session_state.get("best_seed")

    @best_seed.setter
    def best_seed(self, value: Optional[int]):
        st.session_state["best_seed"] = value

    @property
    def best_score(self) -> Optional[float]:
        return st.session_state.get("best_score")

    @best_score.setter
    def best_score(self, value: Optional[float]):
        st.session_state["best_score"] = value

    @property
    def study_hash(self) -> Optional[str]:
        return st.session_state.get("study_hash")

    @study_hash.setter
    def study_hash(self, value: Optional[str]):
        st.session_state["study_hash"] = value

    @property
    def trigger_optimize(self) -> bool:
        return bool(st.session_state.get("trigger_optimize", False))

    @trigger_optimize.setter
    def trigger_optimize(self, value: bool):
        st.session_state["trigger_optimize"] = value

    @property
    def config_weeks(self) -> int:
        return int(st.session_state.get("config_weeks", 4))
        
    @property
    def config_tries(self) -> int:
        return int(st.session_state.get("config_tries", 5))

    @property
    def config_seed(self) -> int:
        return int(st.session_state.get("config_seed", 0))

    @property
    def merge_calendars(self) -> bool:
        return bool(st.session_state.get("merge_calendars", False))

    def clear_results(self):
        """Clear all optimization results."""
        st.session_state["schedule"] = None
        st.session_state["w_result"] = None
        st.session_state["validation"] = None
        st.session_state["fairness"] = None
        st.session_state["best_seed"] = None
        st.session_state["best_score"] = None
        st.session_state["edo_plan"] = None
        st.session_state["staffing"] = None
