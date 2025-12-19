"""
Abstract Base Solver
====================
Defines the interface that all solvers (weekday, weekend) must implement.
This enables polymorphic usage and easier testing via mocks.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Generic, List, Optional, TypeVar

from rota.models.person import Person


class SolverStatus(Enum):
    """Status of solver execution."""
    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    TIMEOUT = "timeout"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass
class SolverResult:
    """Generic result returned by any solver."""
    status: SolverStatus
    solve_time_seconds: float
    message: str = ""
    stats: Dict = None
    
    def __post_init__(self):
        if self.stats is None:
            self.stats = {}
    
    @property
    def is_success(self) -> bool:
        """True if solver found a valid solution."""
        return self.status in (SolverStatus.OPTIMAL, SolverStatus.FEASIBLE)


# Generic type for schedule payloads
TSchedule = TypeVar('TSchedule')


class BaseSolver(ABC, Generic[TSchedule]):
    """
    Abstract base class for all solvers.
    
    Type parameter TSchedule is the specific schedule type
    produced by this solver (e.g., PairSchedule, WeekendResult).
    """
    
    @abstractmethod
    def solve(self) -> TSchedule:
        """
        Execute the solver and return the schedule.
        
        Returns:
            A schedule object specific to the solver implementation.
        """
        pass
    
    @abstractmethod
    def get_status(self) -> SolverStatus:
        """Get the solver status after execution."""
        pass
    
    @abstractmethod
    def get_solve_time(self) -> float:
        """Get the solve time in seconds."""
        pass


class BaseSchedule(ABC):
    """
    Abstract base class for all schedule types.
    
    Ensures consistent interface across different schedule implementations.
    """
    
    @property
    @abstractmethod
    def status(self) -> str:
        """Solver status string."""
        pass
    
    @property
    @abstractmethod
    def weeks(self) -> int:
        """Number of weeks in schedule horizon."""
        pass
    
    @property
    @abstractmethod
    def people_count(self) -> int:
        """Number of people in schedule."""
        pass
    
    @abstractmethod
    def get_person_shifts(self, name: str) -> List:
        """Get all shifts assigned to a person."""
        pass


# Protocol for validation (structural typing alternative)
from typing import Protocol


class Validatable(Protocol):
    """Protocol for objects that can be validated."""
    
    def validate(self) -> List[str]:
        """
        Validate the object.
        
        Returns:
            List of validation error messages (empty if valid).
        """
        ...


class Scoreable(Protocol):
    """Protocol for objects that can be scored."""
    
    def calculate_score(self) -> float:
        """
        Calculate a quality score.
        
        Returns:
            Score value (lower is better by convention).
        """
        ...
