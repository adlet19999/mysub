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

const { selectCalendarArea, toggleCalendarDate } = loadSource(path.join("lib", "calendarSelection.ts"));
const { enrollmentTotal, selectableSessions, isActiveVisit, lessonCount, groupBookingStatus } = loadSource(path.join("lib", "groups.ts"));
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

test("clicking the only selected date clears the selection", () => {
  assert.deepEqual(toggleCalendarDate([keys[8]], keys[8]), []);
});

test("clicking a selected date removes only that date", () => {
  assert.deepEqual(toggleCalendarDate([keys[8], keys[9]], keys[8]), [keys[9]]);
});

test("clicking an unselected date adds it without losing previous dates", () => {
  assert.deepEqual(toggleCalendarDate([keys[8]], keys[9]), [keys[8], keys[9]]);
});

test("a date can be selected again after clearing the last selection", () => {
  assert.deepEqual(toggleCalendarDate(toggleCalendarDate([keys[8]], keys[8]), keys[8]), [keys[8]]);
});

test("group enrollment totals only selected lessons without rounding drift", () => {
  const sessions = [{ id: 1, base_price: "33.34" }, { id: 2, base_price: "33.33" }, { id: 3, base_price: "33.33" }];
  assert.equal(enrollmentTotal(sessions, [1, 2, 3]), 100);
  assert.equal(enrollmentTotal(sessions, [2, 3]), 66.66);
  assert.equal(enrollmentTotal(sessions, []), 0);
});

test("group enrollment excludes cancelled past and full lessons", () => {
  const now = Date.parse("2026-01-01T10:00:00Z");
  const session = { status: "scheduled", available_places: 1, starts_at: "2026-01-02T10:00:00Z" };
  assert.deepEqual(selectableSessions([
    { ...session, id: 1 },
    { ...session, id: 2, status: "cancelled" },
    { ...session, id: 3, available_places: 0 },
    { ...session, id: 4, starts_at: "2025-12-31T10:00:00Z" },
  ], now).map((item) => item.id), [1]);
});

test("participant actions are only offered for active visits", () => {
  assert.equal(isActiveVisit("booked"), true);
  assert.equal(isActiveVisit("pending"), true);
  for (const status of ["cancelled", "completed", "no_show"]) assert.equal(isActiveVisit(status), false);
});

test("group lesson counts use Russian word forms", () => {
  for (const [count, label] of [[1, "занятие"], [2, "занятия"], [5, "занятий"], [11, "занятий"], [14, "занятий"], [21, "занятие"], [22, "занятия"], [115, "занятий"]]) {
    assert.equal(lessonCount(count), `${count} ${label}`);
  }
});

test("stored group cards retain attendance colors even when groups become empty", () => {
  const status = (...statuses) => groupBookingStatus(statuses.map((status) => ({ status })));
  assert.equal(status(), "booked");
  assert.equal(status("cancelled"), "booked");
  assert.equal(status("completed", "booked"), "booked");
  assert.equal(status("completed", "no_show"), "completed");
  assert.equal(status("no_show", "cancelled"), "no_show");
});
