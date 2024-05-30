import streamlit as st
import pandas as pd
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from OlympusTrader.strategy.base_strategy import BaseStrategy

# @st.experimental_rerun()
class Dashboard:
    STRATEGY = None

    def __init__(self, strategy):
        self.STRATEGY = strategy
        st.title("Olympus Trader")
        st.divider()
        


    def show(self):
        # Account Info
        account_col, open_pnl_col, insight_count_col = st.columns(3)
        with account_col:
            st.metric("Balance", self.STRATEGY.account["balance"], delta=0.0)
        with open_pnl_col:
            st.metric("Open PnL", self.STRATEGY.tools.get_all_unrealized_pnl())
        with insight_count_col:
            st.metric("Insights", len(self.STRATEGY.tools.get_filled_insights()))


        st.subheader("Strategy Assets")
        assets = pd.DataFrame(self.STRATEGY.assets).T
        st.dataframe(assets)

        st.subheader("Strategy Positions")
        positions = pd.DataFrame(self.STRATEGY.positions).T
        st.dataframe(positions)

        st.subheader("Strategy Performance Metrics")
        # metrics = pd.DataFrame(self.STRATEGY.metrics).T
        # st.dataframe(metrics)

        st.subheader("Strategy Insights")
        insights = pd.DataFrame(self.STRATEGY.insights).T
        st.dataframe(insights)

