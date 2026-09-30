"""
Common interface every strategy implements.

Design note (matches your 4 backtest configs verbatim): each strategy is
evaluated as a *level* condition, not a crossing event - e.g. "long when fast
SMA is above slow SMA" means buy when that's true and gated by not currently
holding a leg for this entry, sell when it stops being true and a leg is
open. The "gated by position state" part is what stops the app from trying
to re-buy every single day the condition stays true - it only acts on the
day the state changes for THIS entry (flat -> signal true -> buy; open ->
signal false -> sell).
"""
from dataclasses import dataclass, field


@dataclass
class ParamField:
    name: str
    label: str
    type: str  # 'int' | 'float'
    default: float


@dataclass
class SignalResult:
    signal: str          # 'buy' | 'sell' | 'hold'
    price: float
    indicators: dict = field(default_factory=dict)
    reason: str = ""


class Strategy:
    key = "base"
    label = "Base strategy"
    description = ""
    param_fields = []  # list[ParamField]

    @classmethod
    def default_params(cls):
        return {f.name: f.default for f in cls.param_fields}

    @classmethod
    def min_bars_required(cls, params) -> int:
        raise NotImplementedError

    @classmethod
    def evaluate(cls, df, params: dict, in_position: bool) -> SignalResult:
        """
        df: DataFrame of daily bars (open/high/low/close/volume), ascending,
        with at least min_bars_required(params) rows and the most recent
        completed session as the last row.
        """
        raise NotImplementedError
