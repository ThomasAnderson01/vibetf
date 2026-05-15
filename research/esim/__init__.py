"""Daily stock ETF factor research framework."""

from .composite import (
    COMPOSITE_REGISTRY,
    CompositeMethod,
    EqualWeightComposite,
    RollingICComposite,
    get_composite_method,
    register_composite_method,
)
from .config import CompositeConfig, DataConfig, FactorSpec, PortfolioConfig, ResearchConfig
from .experiment import run_experiment
from .pipeline import (
    DEFAULT_STUDY_STEPS,
    Step,
    StudyContext,
    StudyPipeline,
    add_labels,
    compute_factors,
    evaluate_factors,
    filter_eligible,
    load_data,
    normalize_factors,
    prepare_bars,
    run_factor_study,
)
from .portfolio import (
    SELECTION_REGISTRY,
    EqualWeightTopN,
    SelectionStrategy,
    get_selection_strategy,
    register_selection_strategy,
)
from .results import CompositeResult, ExperimentResult, FactorResult, StudyResult

__all__ = [
    "COMPOSITE_REGISTRY",
    "CompositeConfig",
    "CompositeMethod",
    "CompositeResult",
    "DataConfig",
    "DEFAULT_STUDY_STEPS",
    "EqualWeightComposite",
    "EqualWeightTopN",
    "ExperimentResult",
    "FactorSpec",
    "FactorResult",
    "PortfolioConfig",
    "ResearchConfig",
    "SELECTION_REGISTRY",
    "SelectionStrategy",
    "Step",
    "StudyContext",
    "StudyPipeline",
    "StudyResult",
    "add_labels",
    "compute_factors",
    "evaluate_factors",
    "filter_eligible",
    "get_composite_method",
    "get_selection_strategy",
    "load_data",
    "normalize_factors",
    "prepare_bars",
    "register_composite_method",
    "register_selection_strategy",
    "run_experiment",
    "run_factor_study",
    "RollingICComposite",
]
