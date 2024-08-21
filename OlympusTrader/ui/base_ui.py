import streamlit as st
import pandas as pd

from OlympusTrader.strategy.interfaces import IStrategyMode
from OlympusTrader.strategy.base_strategy import BaseStrategy
from OlympusTrader.broker.interfaces import IAccount, IAsset, IPosition
from OlympusTrader.strategy.sharedmemory import SharedStrategyManager
from OlympusTrader.ui.helper.sharedStrategyManager import get_shared_strategy_manager

st.title("Olympus Trader")
st.divider()

def strategy_view(manager: SharedStrategyManager):
    # Get the shared strategy instance
    STRATEGY: BaseStrategy = manager.get_strategy()
    # Account Info
    ACCOUNT: IAccount = manager.get_account()
    STARTING_CASH = float(str(manager.get_starting_cash()))
    ASSETS: dict[str, IAsset] = manager.get_assets()
    POSITIONS:  dict[str, IPosition] = manager.get_positions()
    MODE = manager.get_mode()

    account_col, open_pnl_col, mode_col = st.columns(3)
    with account_col:
        st.metric("Balance", ACCOUNT.get("equity") or 0.0, delta=round(
            ACCOUNT.get("equity") - float(STARTING_CASH), 2) or 0.0)
        # st.metric("Balance", ACCOUNT["equity"] or 0.0, delta=(ACCOUNT["equity"] - STARTING_CASH) or 0.0)
    with open_pnl_col:
        pass
        # st.metric("Open PnL", (STRATEGY.get_variable('tools').get_all_unrealized_pnl()) or 0.0)
    with mode_col:
        st.metric("Mode", MODE.strip("'"))
        pass
        # st.metric("Insights", len(STRATEGY.get_variable('tools').get_filled_insights()) or 0)
    st.subheader("Strategy Insights")
    INSIGHTS = manager.get_insights()
    insights_df = pd.DataFrame.from_dict(INSIGHTS.values())
    if insights_df.empty:
        st.info("No insights")
    else:
        st.dataframe(insights_df)

    st.subheader("Strategy Positions")
    positions_df = pd.DataFrame.from_dict(POSITIONS.values())
    if positions_df.empty:
        st.info("No open positions")
    else:
        positions_df["asset"] = positions_df["asset"].apply(
            lambda x: dict(x)["symbol"])
        st.dataframe(positions_df)

    st.subheader("Strategy Assets")
    assets_df = pd.DataFrame(ASSETS.values())
    st.dataframe(assets_df)


    # st.subheader("Strategy Performance Metrics")
    # # metrics = pd.DataFrame(STRATEGY.metrics).T
    # # st.dataframe(metrics)



try:
    manager = get_shared_strategy_manager()
    if manager:
        strategy_view(manager)
    else:
        st.error("Error connecting to shared memory")
    # st.stop()

    

except Exception as e:
    st.error(f"Error connecting to shared memory: {e}")

# if __name__ == '__main__':
#     dashboard = Dashboard()

#     dashboard.show()
