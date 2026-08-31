// Engine-free adapter pieces. A durable engine resumes a crashed workflow from its last
// completed step, and its soft spot is a step that called a vendor and crashed before the
// step checkpoint committed: on recovery the step re-runs and repeats the side effect.
// guard and Saga close that gap without depending on any particular engine, so they stay
// testable on their own.
//
//   guard(capsule, context, transport, perform)
//       Probe first. If the effect already landed, skip perform() and return Skipped.
//       Call it inside a step so a re-run reconciles before it re-charges.
//
//   Saga
//       Record each effect as its step completes. If the workflow fails, compensate()
//       runs unwind for every recorded effect in reverse order.

import type { Capsule } from "./capsule.ts";
import {
  type CompensationResult,
  type Outcome,
  type Transport,
  reconcile,
  unwind,
} from "./reconcile.ts";

/** The effect had already landed, so guard did not repeat the call. */
export class Skipped {
  readonly capsuleId: string;
  readonly outcome: Outcome;

  constructor(capsuleId: string, outcome: Outcome) {
    this.capsuleId = capsuleId;
    this.outcome = outcome;
  }
}

/** The probe could not tell whether the effect landed, so guard refused to act.
 *
 * Firing a side effect on an unknown answer is a guess, and for money-moving
 * operations a guess in either direction is the bug this library exists to remove.
 * The caller decides how to wait and re-probe: re-throw so the durable engine
 * retries the step later, or catch and re-run guard after a delay. */
export class UnknownOutcome extends Error {
  readonly outcome: Outcome;

  constructor(outcome: Outcome) {
    super(
      `${outcome.capsuleId}: probe returned unknown ` +
        `(evidence ${JSON.stringify(outcome.evidence)}), refusing to run the side effect`,
    );
    this.name = "UnknownOutcome";
    this.outcome = outcome;
  }
}

export interface GuardOptions {
  /** How many extra probes to make on an unknown answer before giving up. */
  unknownRetries?: number;
  /** Seconds to wait between those retries. */
  unknownWait?: number;
  /** Injectable wait, so a test never sleeps for real. */
  sleep?: (seconds: number) => void | Promise<void>;
}

const realSleep = (seconds: number): Promise<void> =>
  new Promise((resolve) => setTimeout(resolve, seconds * 1000));

/** Probe with the capsule, then act only if the effect definitely has not landed.
 *
 * landed skips the call and not_landed runs it. An unknown answer (an outage, a
 * timeout, money still in flight) is never acted on. By default guard throws
 * UnknownOutcome immediately so the engine's own retry policy takes over. Give it
 * unknownRetries and it waits unknownWait seconds and asks again that many times
 * before throwing, a bounded patience rather than an open-ended hang.
 *
 * One freshness caveat stands either way: an eventually consistent probe (Stripe
 * search, for one) can answer not_landed moments after the effect landed, so a
 * recovery path should wait out the vendor's freshness window before trusting a
 * not_landed that follows a crash. */
export async function guard<T>(
  capsule: Capsule,
  context: Record<string, unknown>,
  transport: Transport | undefined,
  perform: () => T | Promise<T>,
  options: GuardOptions = {},
): Promise<Skipped | Awaited<T>> {
  const attempts = Math.max(0, Math.trunc(options.unknownRetries ?? 0)) + 1;
  const wait = options.unknownWait ?? 2.0;
  const sleep = options.sleep ?? realSleep;
  let outcome: Outcome | undefined;
  for (let attempt = 0; attempt < attempts; attempt++) {
    outcome = await reconcile(capsule, context, transport);
    if (outcome.status === "landed") return new Skipped(capsule.id, outcome);
    if (outcome.status === "not_landed") return await perform();
    if (attempt + 1 < attempts) await sleep(wait);
  }
  throw new UnknownOutcome(outcome as Outcome);
}

interface SagaStep {
  capsule: Capsule;
  context: Record<string, unknown>;
  transport?: Transport;
}

/** A record of completed effects that can be walked back on failure.
 *
 * The journal lives in process memory. It survives an exception inside the
 * workflow, which is the case it exists for. Under a deterministic-replay engine
 * the record() calls are replayed on recovery, but only when record() lives in
 * workflow-body code: engines skip completed steps on recovery, so a record()
 * inside a step body never replays. Call record() in the workflow with the step's
 * return value, and create one Saga per workflow invocation. A bare process crash
 * with no replaying engine loses the journal either way, so if it must outlive the
 * process, persist each recorded context in your engine's own store. */
export class Saga {
  private steps: SagaStep[] = [];

  record(
    capsule: Capsule,
    context: Record<string, unknown>,
    transport?: Transport,
  ): void {
    this.steps.push({ capsule, context, transport });
  }

  /** Run unwind for every recorded effect, most recent first.
   *
   * One bad step must not strand the rest: an unwind that throws is captured as a
   * CompensationResult with status "error" and the walk continues, so every
   * recorded effect gets its attempt and the caller sees the full list. */
  async compensate(): Promise<CompensationResult[]> {
    const results: CompensationResult[] = [];
    for (let i = this.steps.length - 1; i >= 0; i--) {
      const step = this.steps[i];
      try {
        results.push(await unwind(step.capsule, step.context, step.transport));
      } catch (err) {
        results.push({
          status: "error",
          capsuleId: step.capsule.id,
          evidence: { error: String(err) },
        });
      }
    }
    return results;
  }

  get size(): number {
    return this.steps.length;
  }
}
