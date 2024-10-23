import os
from dotenv import load_dotenv

from OlympusTrader.strategy.sharedmemory import SharedStrategyManager

def get_shared_strategy_manager():
    """Get the shared strategy manager instance"""
    try:
        load_dotenv()
        assert os.getenv('SSM_HOST') and os.getenv(
            'SSM_PASSWORD'), "Please set SSM_HOST and SSM_PASSWORD environment variables"

        # print("Connecting to Shared Strategy Manager...")

        manager = SharedStrategyManager(address=(
            os.getenv("SSM_HOST"), 50000), authkey=os.getenv("SSM_PASSWORD").encode())

        manager.connect()
        
        return manager

    except Exception as e:
        return None


def get_strategiesPath():
    path = "."
    if os.getenv('STRATEGIES_PATH'):
        path = os.getenv('STRATEGIES_PATH')
    else:
        print("Please set STRATEGIES_PATH environment variable. Using default path '.'")

    return path
