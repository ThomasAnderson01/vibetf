"""Daily stock ETF factor research framework."""

from .config import CompositeConfig, DataConfig, FactorSpec, PortfolioConfig, ResearchConfig
from .experiment import run_experiment
from .pipeline import run_factor_study
from .results import CompositeResult, ExperimentResult, FactorResult, StudyResult

__all__ = [
    "CompositeConfig",
    "CompositeResult",
    "DataConfig",
    "ExperimentResult",
    "FactorSpec",
    "FactorResult",
    "PortfolioConfig",
    "ResearchConfig",
    "run_experiment",
    "StudyResult",
    "run_factor_study",
]
