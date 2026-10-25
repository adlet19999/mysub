const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const ts = require("typescript");

function loadSource(relativePath) {
  const filename = path.join(__dirname, "..", "src", relativePath);
  const source = fs.readFileSync(filename, "utf8");
  const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } });
  const module = { exports: {} };
  new Function("module", "exports", "require", outputText)(module, module.exports, require);
  return module.exports;
}

const { selectCalendarArea } = loadSource(path.join("lib", "calendarSelection.ts"));
const keys = Array.from({ length: 42 }, (_, index) => `day-${index}`);

test("calendar drag selects the rectangle, not a continuous date range", () => {
  assert.deepEqual(new Set(selectCalendarArea(keys, 8, 17, [], false)), new Set([8, 9, 10, 15, 16, 17].map((index) => keys[index])));
});

test("calendar reverse drag selects the same rectangle", () => {
  assert.deepEqual(selectCalendarArea(keys, 17, 8, [], false), selectCalendarArea(keys, 8, 17, [], false));
});

test("calendar additive selection preserves previous dates without duplicates", () => {
  assert.deepEqual(new Set(selectCalendarArea(keys, 8, 9, [keys[0], keys[8]], true)), new Set([keys[0], keys[8], keys[9]]));
});

test("calendar regular selection replaces the previous area", () => {
  assert.deepEqual(selectCalendarArea(keys, 41, 41, [keys[0]], false), [keys[41]]);
});

test("calendar selection supports the entire six-week calendar", () => {
  assert.equal(selectCalendarArea(keys, 0, 41, [], false).length, 42);
});
