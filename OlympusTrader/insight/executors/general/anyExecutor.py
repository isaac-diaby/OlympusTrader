from ..base_executor import BaseExecutor
from ...insight import InsightState


class AnyExecutor(BaseExecutor):
    """
    ### Any Executor
    This executor is an operator on executors that passes if any of the sub-executors pass.


    Author:
        @isaac-diaby
    """

    executors: list[BaseExecutor]

    def __init__(
        self,
        strategy,
        insightState: InsightState,
        executors: list[BaseExecutor],
        **kwargs,
    ):
        assert len(executors) > 0, "You must provide at least one executor."
        assert all(
            isinstance(executor, BaseExecutor) for executor in executors
        ), "All executors must be of type BaseExecutor."
        super().__init__(strategy, insightState, "1.0", **kwargs)
        self.executors = executors

    def run(self, insight):
        try:
            collectErrors = []
            for executor in self.executors:
                if not executor.should_run(insight):
                    continue
                result = executor.run(insight)
                if not result.success:
                    collectErrors.append(result.message)
                    continue
                if result.passed:
                    return self.returnResults(
                        True,
                        True,
                        f"Executor {executor.__class__.__name__} passed. {result.message}",
                    )
            self.changeState(insight, InsightState.REJECTED, f"Errors: {collectErrors}")
            return self.returnResults(
                False, True, f"No executor passed. Errors: {collectErrors}"
            )
        except Exception as e:
            return self.returnResults(False, False, f"Error running executor: {e}")

    def add_executor(self, executor: BaseExecutor):
        self.executors.append(executor)
        return self.executors

    def remove_executor(self, executor: BaseExecutor):
        self.executors.remove(executor)
        return self.executors
