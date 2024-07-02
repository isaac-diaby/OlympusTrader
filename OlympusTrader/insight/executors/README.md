# Insight Executors

```python
from ..base_executor import BaseExecutor
from ...insight import InsightState

class MinimumRiskToRewardExecutor(BaseExecutor):
    def __init__(self, strategy, insight):
        super().__init__(strategy, insight, InsightState.NEW, "1.0")
        # Add the required parameters here

    def run(self):
        # Implement the logic here
        pass
```