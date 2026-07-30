from typing import override

from quant_ranger import Status, UpdateItem, UpdateOutcome
from quant_ranger.scanners import RepositoriesScanner
from quant_ranger.updaters import CustomFileUpdater, UpdateTask


class SimpleCustomTask(UpdateTask[UpdateItem]):
    @override
    def run(self) -> UpdateOutcome:
        self.context.logger.info("Simple custom updater ran.")
        return UpdateOutcome(
            result=Status.UP_TO_DATE,
            message="No changes made.",
        )


class SimpleCustomUpdater(CustomFileUpdater[UpdateItem]):
    name = "simple-custom"
    description = "Example updater that scans repositories and makes no changes."
    scanner = RepositoriesScanner()
    task_type = SimpleCustomTask


updater = SimpleCustomUpdater()
