// Node 22.18+ can execute this TypeScript compatibility reader directly.
// This validates interchange data; it is deliberately not a second SDK.
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import assert from "node:assert/strict";

const source = readFileSync(process.argv[2], "utf8");
const spans = new WeakMap<object, string>();
let position = 0;
function whitespace() { while (/\s/.test(source[position] ?? "x")) position++; }
function parse(): any {
  whitespace();
  const start = position, char = source[position];
  if (char === '"') {
    position++;
    while (position < source.length) {
      if (source[position++] === "\\") position++;
      else if (source[position - 1] === '"') return JSON.parse(source.slice(start, position));
    }
    throw new Error("Unterminated string");
  }
  if (char === "{" || char === "[") {
    const value: any = char === "{" ? Object.create(null) : [];
    const end = char === "{" ? "}" : "]";
    position++; whitespace();
    if (source[position] !== end) {
      while (true) {
        if (char === "{") {
          assert.equal(source[position], '"');
          const key = parse(); whitespace();
          assert(!Object.hasOwn(value, key), "Duplicate key");
          assert.equal(source[position++], ":"); value[key] = parse();
        } else value.push(parse());
        whitespace();
        if (source[position] === end) break;
        assert.equal(source[position++], ","); whitespace();
      }
    }
    assert.equal(source[position++], end);
    spans.set(value, source.slice(start, position)); return value;
  }
  const token = /^(?:true|false|null|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)/.exec(source.slice(position))?.[0];
  assert(token, "Invalid JSON token"); position += token.length;
  if (/^-?[0-9]+$/.test(token)) {
    const integer = BigInt(token);
    return integer >= -9007199254740991n && integer <= 9007199254740991n ? Number(integer) : integer;
  }
  const result = JSON.parse(token);
  assert(typeof result !== "number" || Number.isFinite(result)); return result;
}
function verify(value: object, digest: string) {
  assert.equal(createHash("sha256").update(spans.get(value)!, "utf8").digest("hex"), digest);
}
function int64(value: any): bigint {
  assert(typeof value === "bigint" || (typeof value === "number" && Number.isSafeInteger(value)));
  const result = BigInt(value);
  assert(result >= -(2n ** 63n) && result < 2n ** 63n); return result;
}
const bundle = parse(); whitespace(); assert.equal(position, source.length);
assert.equal(bundle.payload.format, 1);
verify(bundle.payload, bundle.checksum);
const objects = new Map<string, Set<string>>();
const names = new Set<string>();
const integers: string[] = [];
let binaryBytes = 0;
for (const object of bundle.payload.objects) {
  verify(object.rows, object.checksum);
  assert(!names.has(object.schema.name)); names.add(object.schema.name);
  const kind = object.schema.op;
  assert(["collection", "table", "relationship"].includes(kind));
  if (kind !== "relationship") {
    const ids = new Set<string>();
    for (const row of object.rows) {
      assert.equal(typeof row.id, "string");
      assert(!ids.has(row.id));
      ids.add(row.id);
      if (kind === "collection") {
        assert(int64(row.version) > 0n);
        assert(row.body !== null && !Array.isArray(row.body) && typeof row.body === "object");
      }
      if (kind === "table") {
        for (const [column, type] of Object.entries(object.schema.columns)) {
          if (row[column] === null) continue;
          if (type === "integer") integers.push(int64(row[column]).toString());
          if (type === "bytes") {
            assert.deepEqual(Object.keys(row[column]), ["base64"]);
            const bytes = Buffer.from(row[column].base64, "base64");
            assert.equal(bytes.toString("base64"), row[column].base64); binaryBytes += bytes.length;
          }
        }
      }
    }
    objects.set(object.schema.name, ids);
  }
}
let links = 0;
for (const object of bundle.payload.objects) {
  if (object.schema.op === "relationship") {
    const pairs = new Set<string>();
    for (const row of object.rows) {
      assert(objects.get(object.schema.source)?.has(row.source_id));
      assert(objects.get(object.schema.target)?.has(row.target_id));
      const pair = JSON.stringify([row.source_id, row.target_id]);
      assert(!pairs.has(pair)); pairs.add(pair);
      links++;
    }
  }
}
for (const revision of bundle.payload.migrations) {
  assert.equal(createHash("sha256").update(revision.operations).digest("hex"), revision.checksum);
}
// Hash original canonical UTF-8 tokens, preserving numeric spellings and Unicode
// key order. This proof reader accepts exporter output, not reformatted JSON.
console.log(JSON.stringify({ format: 1, storages: objects.size, links, integers, binaryBytes,
                            checksums: "verified", interoperability: "canonical logical read" }));
