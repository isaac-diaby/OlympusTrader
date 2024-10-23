from dataclasses import dataclass


@dataclass
class STORE_MAP():
    id: str
@dataclass
class STRATEGY_STORE_MAPPINGS():
    account = STORE_MAP("strategy-data-store-account")
    mode = STORE_MAP("strategy-data-store-mode")
    assets = STORE_MAP("strategy-data-store-assets")
    positions = STORE_MAP("strategy-data-store-positions")
    insights = STORE_MAP("strategy-data-store-insights")
    history = STORE_MAP("strategy-data-store-history")
    metrics = STORE_MAP("strategy-data-store-metrics")
    time = STORE_MAP("strategy-data-store-time")

@dataclass
class STRATEGY_SYNC_MAPPING(STORE_MAP):
    id = "strategy-sync-store"