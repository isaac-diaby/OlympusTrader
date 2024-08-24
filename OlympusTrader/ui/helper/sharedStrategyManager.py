import os
import streamlit as st
from dotenv import load_dotenv

from OlympusTrader.strategy.sharedmemory import SharedStrategyManager

# Create a shared memory manager


def get_shared_strategy_manager():
    try:

        load_dotenv()
        assert os.getenv('SSM_HOST') and os.getenv(
            'SSM_PASSWORD'), "Please set SSM_HOST and SSM_PASSWORD environment variables"

        manager = SharedStrategyManager(address=(
            os.getenv("SSM_HOST"), 50000), authkey=os.getenv("SSM_PASSWORD").encode())
        manager.connect()

        return manager
        # yield manager

    except Exception as e:
        st.error(f"Error connecting to shared memory: {e}")
        return None


def get_strategiesPath():
    path = "."
    if os.getenv('STRATEGIES_PATH'):
        path = os.getenv('STRATEGIES_PATH')
    else:
        print("Please set STRATEGIES_PATH environment variable. Using default path '.'")

    return path
