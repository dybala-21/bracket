from __future__ import annotations

from typing import Any

from bracket.adapters.common.base import BaseAdapter
from bracket.core.contracts import ExecutionContract
from bracket.core.harness import RunHandle


class GenericAdapter(BaseAdapter):
    """Minimal adapter for frameworks without a dedicated integration.

    Delegates directly to the Harness with no framework-specific
    event translation.
    """

    @property
    def framework_name(self) -> str:
        return "generic"

    def wrap_run(self, contract: ExecutionContract, **kwargs: Any) -> RunHandle:
        return self._harness.start_run(contract)

    def finalize_run(self, run: RunHandle, **kwargs: Any) -> Any:
        return self._harness.finish_run_sync(run, final_output=kwargs.get("final_output"), probes=kwargs.get("probes"))


__all__ = ["GenericAdapter"]
