from multiprocessing.managers import BaseManager, ValueProxy, DictProxy


class SharedStrategyManager(BaseManager):
    pass


# Register the shared memory strategy class
SharedStrategyManager.register('get_strategy')
# Register the shared memory account data
SharedStrategyManager.register('get_account')
# Register the shared memory account data
SharedStrategyManager.register('get_starting_cash')
# Register the shared memory for the strategy mode
SharedStrategyManager.register('get_mode')
# Register the shared memory for the strategy assets
SharedStrategyManager.register('get_assets')
# Register the shared memory for the strategy positions
SharedStrategyManager.register('get_positions')
# Register the shared memory for the strategy insights
SharedStrategyManager.register('get_insights')
