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

import time
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


class UnknownOutcome(RuntimeError):
    """The probe could not tell whether the effect landed, so guard refused to act.

    Firing a side effect on an unknown answer is a guess, and for money-moving
    operations a guess in either direction is the bug this library exists to remove.
    The caller decides how to wait and re-probe: re-raise so the durable engine
    retries the step later, or catch and re-run guard after a delay.
    """

    def __init__(self, outcome: Outcome):
        super().__init__(
            f"{outcome.capsule_id}: probe returned unknown "
            f"(evidence {outcome.evidence}), refusing to run the side effect")
        self.outcome = outcome


def guard(
        capsule: Capsule,
        context: dict,
        transport: Transport | None,
        do: Callable[[], object],
        unknown_retries: int = 0,
        unknown_wait: float = 2.0,
        sleep: Callable[[float], None] = time.sleep) -> object:
    """Probe with the capsule, then act only if the effect definitely has not landed.

    landed skips the call and not_landed runs it. An unknown answer (an outage, a
    timeout, money still in flight) is never acted on. By default guard raises
    UnknownOutcome immediately so the engine's own retry policy takes over. Give it
    unknown_retries and it will wait unknown_wait seconds and ask again that many
    times before raising, a bounded patience rather than an open-ended hang.

    One freshness caveat stands either way: an eventually consistent probe (Stripe
    search, for one) can answer not_landed moments after the effect landed, so a
    recovery path should wait out the vendor's freshness window before trusting a
    not_landed that follows a crash.
    """
    attempts = max(0, int(unknown_retries)) + 1
    outcome = None
    for attempt in range(attempts):
        outcome = reconcile(capsule, context, transport=transport)
        if outcome.landed:
            return Skipped(capsule.id, outcome)
        if outcome.not_landed:
            return do()
        if attempt + 1 < attempts:
            sleep(unknown_wait)
    raise UnknownOutcome(outcome)


@dataclass
class _Step:
    capsule: Capsule
    context: dict
    transport: Transport | None


@dataclass
class Saga:
    """A record of completed effects that can be walked back on failure.

    The journal lives in process memory. It survives an exception inside the
    workflow, which is the case it exists for, and under a deterministic-replay
    engine the record() calls are replayed on recovery, but only when record()
    lives in WORKFLOW-BODY code. Engines skip completed steps on recovery, so a
    record() inside a step body never replays: call record() in the workflow with
    the step's return value, and create one Saga per workflow invocation. A bare
    process crash with no replaying engine loses the journal either way, so if it
    must outlive the process, persist each recorded context in your engine's own
    store."""

    _steps: list[_Step] = field(default_factory=list)

    def record(
            self,
            capsule: Capsule,
            context: dict,
            transport: Transport | None = None) -> None:
        self._steps.append(_Step(capsule, context, transport))

    def compensate(self) -> list[CompensationResult]:
        """Run unwind for every recorded effect, most recent first.

        One bad step must not strand the rest: an unwind that raises is captured
        as a CompensationResult with status "error" and the walk continues, so
        every recorded effect gets its attempt and the caller sees the full list.
        """
        results = []
        for step in reversed(self._steps):
            try:
                results.append(
                    unwind(step.capsule, step.context, transport=step.transport))
            except Exception as exc:
                results.append(CompensationResult(
                    "error", step.capsule.id, {"error": str(exc)}))
        return results

    def __len__(self) -> int:
        return len(self._steps)
