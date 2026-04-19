from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contracts import ExecutionContract
from .events import EvidenceEvent
from .evidence import EvidenceSummary
from .verdict import Verdict


@dataclass
class ReplayManifest:
    """Describes what replay modes a run artifact supports and where to find the data."""

    run_id: str
    schema_version: str = "1"
    requirement_set_version: str = ""
    verdict_engine_version: str = "1.0.0"
    projection_engine_version: str = "1.0.0"
    adapter_version: str = ""
    probe_bundle_version: str = "builtin@0.1.0"
    supported_modes: list[str] = field(default_factory=lambda: ["trace_replay"])
    default_mode: str = "trace_replay"
    event_log_ref: str = "events.jsonl"
    verdict_ref: str = "verdict.json"
    probe_results_ref: str = "probes.json"
    artifacts: list[dict[str, str]] = field(default_factory=list)
    llm_recording_ref: str | None = None
    tool_stub_bundle_ref: str | None = None
    environment_snapshot_ref: str | None = None
    session_snapshot_ref: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "run_id": self.run_id,
            "schema_version": self.schema_version,
            "requirement_set_version": self.requirement_set_version,
            "verdict_engine_version": self.verdict_engine_version,
            "projection_engine_version": self.projection_engine_version,
            "adapter_version": self.adapter_version,
            "probe_bundle_version": self.probe_bundle_version,
            "supported_modes": self.supported_modes,
            "default_mode": self.default_mode,
            "event_log_ref": self.event_log_ref,
            "verdict_ref": self.verdict_ref,
            "probe_results_ref": self.probe_results_ref,
            "artifacts": self.artifacts,
        }
        if self.llm_recording_ref:
            d["llm_recording_ref"] = self.llm_recording_ref
        if self.tool_stub_bundle_ref:
            d["tool_stub_bundle_ref"] = self.tool_stub_bundle_ref
        if self.environment_snapshot_ref:
            d["environment_snapshot_ref"] = self.environment_snapshot_ref
        if self.session_snapshot_ref:
            d["session_snapshot_ref"] = self.session_snapshot_ref
        if self.notes:
            d["notes"] = self.notes
        return d


@dataclass
class RunArtifact:
    """Complete record of a single execution run.

    Contains the contract, all evidence events, probe results, the
    computed verdict, and a replay manifest. Can be saved to and
    loaded from a directory of JSON files.
    """

    run_id: str
    contract: ExecutionContract
    events: list[EvidenceEvent]
    summary: EvidenceSummary
    probe_results: list[dict[str, Any]]
    verdict: Verdict
    replay_manifest: ReplayManifest
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def outcome(self) -> Any:
        return self.verdict.outcome

    @property
    def missing_requirement_ids(self) -> list[str]:
        return self.verdict.missing_requirement_ids

    def save(self, base_dir: str | Path) -> Path:
        """Persist the artifact to base_dir/runs/<run_id>/.

        All writes go through the self._write() helper, so a future
        ArtifactStore protocol can redirect them to S3, GCS, or similar.
        """
        base = Path(base_dir)
        run_dir = base / "runs" / self.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        self._write(run_dir / "contract.json", json.dumps(self.contract.to_dict(), indent=2, ensure_ascii=False))

        event_lines = "".join(json.dumps(event.to_dict(), ensure_ascii=False) + "\n" for event in self.events)
        self._write(run_dir / "events.jsonl", event_lines)

        self._write(run_dir / "summary.json", json.dumps(self.summary.to_dict(), indent=2, ensure_ascii=False))
        self._write(run_dir / "probes.json", json.dumps(self.probe_results, indent=2, ensure_ascii=False))
        self._write(run_dir / "verdict.json", json.dumps(self.verdict.to_dict(), indent=2, ensure_ascii=False))
        self._write(run_dir / "replay.json", json.dumps(self.replay_manifest.to_dict(), indent=2, ensure_ascii=False))

        if self.metadata:
            self._write(run_dir / "metadata.json", json.dumps(self.metadata, indent=2, ensure_ascii=False))

        return run_dir

    def _write(self, path: Path, content: str) -> None:
        """Single write sink. Swap this method out to retarget writes to an ArtifactStore."""
        path.write_text(content)
        with contextlib.suppress(OSError):
            path.chmod(0o600)

    @classmethod
    def load_events(cls, run_dir: str | Path) -> list[EvidenceEvent]:
        events_path = Path(run_dir) / "events.jsonl"
        events = []
        with events_path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(EvidenceEvent.from_dict(json.loads(line)))
        return events

    @classmethod
    def load(cls, run_dir: str | Path) -> RunArtifact:
        run_dir = Path(run_dir)

        contract_data = json.loads((run_dir / "contract.json").read_text())
        contract = ExecutionContract.from_dict(contract_data)

        events = cls.load_events(run_dir)

        summary_data = json.loads((run_dir / "summary.json").read_text())
        summary = EvidenceSummary(**summary_data)

        probe_results = json.loads((run_dir / "probes.json").read_text())

        verdict_data = json.loads((run_dir / "verdict.json").read_text())
        verdict = Verdict.from_dict(verdict_data)

        replay_data = json.loads((run_dir / "replay.json").read_text())
        replay_manifest = ReplayManifest(
            **{k: v for k, v in replay_data.items() if k in ReplayManifest.__dataclass_fields__}
        )

        metadata_path = run_dir / "metadata.json"
        metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}

        return cls(
            run_id=replay_data.get("run_id", run_dir.name),
            contract=contract,
            events=events,
            summary=summary,
            probe_results=probe_results,
            verdict=verdict,
            replay_manifest=replay_manifest,
            metadata=metadata,
        )
