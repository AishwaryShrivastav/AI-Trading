"""Signal generation strategies."""
from .base import SignalBase
from .momentum import MomentumStrategy
from .mean_reversion import MeanReversionStrategy
from .extra import (
    RSIDivergenceStrategy,
    BollingerSqueezeStrategy,
    FiftyTwoWeekHighStrategy,
    NiftyETFBaselineStrategy,
)

__all__ = [
    "SignalBase",
    "MomentumStrategy",
    "MeanReversionStrategy",
    "RSIDivergenceStrategy",
    "BollingerSqueezeStrategy",
    "FiftyTwoWeekHighStrategy",
    "NiftyETFBaselineStrategy",
]
