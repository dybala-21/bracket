from __future__ import annotations

from typing import Any

from .base import Probe


class ProbeRunner:
    """Executes a list of probes and collects results.

    Exceptions raised by individual probes are caught and reported
    as failures rather than propagated.
    """

    def run_all(self, probes: list[Probe]) -> list[dict[str, Any]]:
        results = []
        for probe in probes:
            try:
                result = probe.execute()
            except Exception as exc:
                result = {
                    "probe_name": probe.name,
                    "passed": False,
                    "detail": f"Probe raised exception: {exc}",
                    "error": str(exc),
                }
            results.append(result)
        return results

    def run_all_passed(self, probes: list[Probe]) -> bool:
        return all(r.get("passed", False) for r in self.run_all(probes))
