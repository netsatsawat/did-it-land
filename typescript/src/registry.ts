// Load the generated corpus and index it by id.

import { capsuleFromDoc } from "./capsule.ts";
import type { Capsule } from "./capsule.ts";
import { CORPUS } from "./corpus.generated.ts";
import { EffectError } from "./reconcile.ts";

export class Registry {
  byId: Map<string, Capsule>;

  constructor(capsules: Capsule[]) {
    this.byId = new Map();
    for (const cap of capsules) {
      if (this.byId.has(cap.id)) throw new EffectError(`duplicate capsule id '${cap.id}'`);
      this.byId.set(cap.id, cap);
    }
  }

  get(id: string): Capsule {
    const cap = this.byId.get(id);
    if (!cap) {
      const known = [...this.byId.keys()].sort().join(", ") || "none";
      throw new EffectError(`no capsule '${id}' (have: ${known})`);
    }
    return cap;
  }

  all(): Capsule[] {
    return [...this.byId.values()];
  }

  ids(): string[] {
    return [...this.byId.keys()].sort();
  }

  get size(): number {
    return this.byId.size;
  }
}

export function bundled(): Registry {
  return new Registry(CORPUS.map((doc, i) => capsuleFromDoc(doc, `capsule[${i}]`)));
}
