// Node 22.18+ can execute this TypeScript compatibility reader directly.
// This validates interchange data; it is deliberately not a second SDK.
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import assert from "node:assert/strict";

function canonical(value: any): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
  return "{" + Object.keys(value).sort().map(k => JSON.stringify(k) + ":" + canonical(value[k])).join(",") + "}";
}

const bundle = JSON.parse(readFileSync(process.argv[2], "utf8"));
assert.equal(bundle.payload.format, 1);
const objects = new Map<string, Set<string>>();
for (const object of bundle.payload.objects) {
  const kind = object.schema.op;
  if (kind !== "relationship") {
    const ids = new Set<string>();
    for (const row of object.rows) {
      assert.equal(typeof row.id, "string");
      assert(!ids.has(row.id));
      ids.add(row.id);
      if (kind === "collection") {
        assert(Number.isSafeInteger(row.version) && row.version > 0);
        assert(row.body !== null && !Array.isArray(row.body) && typeof row.body === "object");
      }
    }
    objects.set(object.schema.name, ids);
  }
}
let links = 0;
for (const object of bundle.payload.objects) {
  if (object.schema.op === "relationship") {
    for (const row of object.rows) {
      assert(objects.get(object.schema.source)?.has(row.source_id));
      assert(objects.get(object.schema.target)?.has(row.target_id));
      links++;
    }
  }
}
// Checksum verification uses the exact canonical payload bytes from the file in the
// Python validator. JSON numeric spellings (1.0 vs 1) are not stable across runtimes;
// this harness intentionally validates identities, envelopes and relationships.
console.log(JSON.stringify({ format: 1, storages: objects.size, links, interoperability: "sequential logical read" }));
