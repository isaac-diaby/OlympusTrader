import os
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

from OlympusTrader.strategy.sharedmemory import SharedStrategyManager
from OlympusTrader.utils.interfaces import IStrategyMode
from OlympusTrader.strategy.base_strategy import BaseStrategy

# if TYPE_CHECKING:

load_dotenv()
assert os.getenv('SSM_HOST') and os.getenv(
    'SSM_PASSWORD'), "Please set SSM_HOST and SSM_PASSWORD environment variables"


st.title("Olympus Trader")
st.divider()


# Create a shared memory manager
try:
    manager = SharedStrategyManager(address=(
        os.getenv('SSM_HOST'), 50000), authkey=os.getenv('SSM_PASSWORD').encode())
    manager.connect()
except Exception as e:
    st.error(f"Error connecting to shared memory: {e}")
    # st.stop()

# Get the shared strategy instance
STRATEGY: BaseStrategy = manager.get_strategy()

# Account Info
MODE: IStrategyMode = STRATEGY.get_variable('MODE')
account_col, open_pnl_col, mode_col = st.columns(3)
with account_col:
    st.metric("Balance", STRATEGY.get_variable(
        'account')["equity"] or 0.0, delta=0.0)
with open_pnl_col:
    pass
    # st.metric("Open PnL", (STRATEGY.get_variable('tools').get_all_unrealized_pnl()) or 0.0)
with mode_col:
    st.metric("Mode", MODE.value)
    pass
    # st.metric("Insights", len(STRATEGY.get_variable('tools').get_filled_insights()) or 0)

st.subheader("Strategy Assets")
assets = pd.DataFrame(STRATEGY.get_variable('assets')).T
st.dataframe(assets)

st.subheader("Strategy Positions")
positions = pd.DataFrame(STRATEGY.get_variable('positions')).T
st.dataframe(positions)

st.subheader("Strategy Performance Metrics")
# metrics = pd.DataFrame(STRATEGY.metrics).T
# st.dataframe(metrics)

st.subheader("Strategy Insights")
insights = STRATEGY.get_variable('insights')
insights

# if __name__ == '__main__':
#     dashboard = Dashboard()

#     dashboard.show()
