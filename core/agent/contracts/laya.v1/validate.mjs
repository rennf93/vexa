#!/usr/bin/env node
/** gate:schema for laya.v1 — golden `<Shape>.<case>.json` validates against #/$defs/<Shape>. */
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { readdirSync, readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const schema = JSON.parse(readFileSync(join(HERE, "laya.schema.json"), "utf8"));
const ajv = new Ajv2020({ strict: false, allErrors: true });
addFormats(ajv);
ajv.addSchema(schema);

const dir = join(HERE, "golden");
const files = readdirSync(dir).filter((n) => n.endsWith(".json"));
let failures = 0;
for (const f of files) {
  const golden = JSON.parse(readFileSync(join(dir, f), "utf8"));
  const shape = f.split(".")[0];
  if (!schema.$defs[shape]) {
    console.error(`laya.v1 golden ${f}: no $defs/${shape}`);
    failures += 1;
    continue;
  }
  const ok = ajv.validate({ $ref: `https://vexa.ai/schemas/laya.v1#/$defs/${shape}` }, golden);
  if (!ok) {
    console.error(`laya.v1 golden ${f} INVALID:`, ajv.errorsText());
    failures += 1;
  }
}
if (failures) process.exit(1);
console.log(`laya.v1: ${files.length} goldens OK`);
