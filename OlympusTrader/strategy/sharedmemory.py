from multiprocessing.managers import BaseManager

class SharedStrategyManager(BaseManager): pass

# Register the shared memory strategy class
SharedStrategyManager.register('get_strategy')
# Register the shared memory account data
SharedStrategyManager.register('get_account')
