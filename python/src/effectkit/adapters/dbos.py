"""DBOS reference adapter.

DBOS resumes a crashed workflow from its last completed step. Its soft spot is a step
that called a vendor and crashed before the step checkpoint committed: on recovery the
step re-runs and repeats the side effect. This adapter closes that gap with two pieces
that do not depend on DBOS being installed, so they stay testable on their own:

  guard(capsule, context, transport, do)
      Probe first. If the effect already landed, skip do() and return Skipped. Use it
      inside a @DBOS.step so a re-run reconciles before it re-charges.

  Saga
      Record each effect as its step completes. If the workflow fails, compensate()
      runs unwind for every recorded effect in reverse order.

See examples/dbos_charge.py for the wiring inside a real DBOS workflow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..capsule import Capsule
from ..reconcile import CompensationResult, Outcome, reconcile, unwind
from ..transport import Transport


@dataclass(frozen=True)
class Skipped:
    """The effect had already landed, so guard did not repeat the call."""

    capsule_id: str
    outcome: Outcome


def guard(
        capsule: Capsule,
        context: dict,
        transport: Transport | None,
        do: Callable[[], object]) -> object:
    """Probe with the capsule, then act only if the effect has not already landed."""
    outcome = reconcile(capsule, context, transport=transport)
    if outcome.landed:
        return Skipped(capsule.id, outcome)
    return do()


@dataclass
class _Step:
    capsule: Capsule
    context: dict
    transport: Transport | None


@dataclass
class Saga:
    """A record of completed effects that can be walked back on failure."""

    _steps: list[_Step] = field(default_factory=list)

    def record(
            self,
            capsule: Capsule,
            context: dict,
            transport: Transport | None = None) -> None:
        self._steps.append(_Step(capsule, context, transport))

    def compensate(self) -> list[CompensationResult]:
        """Run unwind for every recorded effect, most recent first."""
        results = []
        for step in reversed(self._steps):
            results.append(unwind(step.capsule, step.context, transport=step.transport))
        return results

    def __len__(self) -> int:
        return len(self._steps)
