const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const ts = require("typescript");
const { webcrypto } = require("node:crypto");

function loadSource(relativePath, cryptoSource = webcrypto) {
  const filename = path.join(__dirname, "..", "src", relativePath);
  const source = fs.readFileSync(filename, "utf8");
  const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } });
  const module = { exports: {} };
  new Function("module", "exports", "require", "crypto", outputText)(module, module.exports, require, cryptoSource);
  return module.exports;
}

const { selectCalendarArea, toggleCalendarDate } = loadSource(path.join("lib", "calendarSelection.ts"));
const { enrollmentTotal, selectableSessions, isActiveVisit, lessonCount, groupBookingStatus } = loadSource(path.join("lib", "groups.ts"));
const keys = Array.from({ length: 42 }, (_, index) => `day-${index}`);
const { createRequestId } = loadSource(path.join("lib", "requestId.ts"));
const { applyDefaultVisitTime, changeVisitTime } = loadSource(path.join("lib", "recurringVisits.ts"));
const { validScheduleDate, scheduleHref, scheduleReturnHref, calendarBookingVisible } = loadSource(path.join("lib", "scheduleNavigation.ts"));
const { restaurantCalendarSegments } = loadSource(path.join("lib", "restaurant.ts"));
const { readApiResponse } = loadSource(path.join("lib", "apiResponse.ts"));

test("restaurant HTML errors show HTTP status instead of a JSON syntax error or raw HTML", async () => {
  for (const status of [404, 500, 502, 503]) {
    const response = new Response("<!DOCTYPE html><html>private upstream details</html>", { status });
    await assert.rejects(readApiResponse(response, "Не удалось сохранить бронь"), (error) => {
      assert.equal(error instanceof SyntaxError, false);
      assert.match(error.message, new RegExp(`HTTP ${status}`));
      assert.match(error.message, /Не удалось сохранить бронь/);
      assert.doesNotMatch(error.message, /private upstream|DOCTYPE|Unexpected token/);
      return true;
    });
  }
});

test("restaurant JSON business errors retain the server's explanation", async () => {
  for (const payload of [{ message: "Столик занят" }, { detail: "Столик занят" }, { error: { message: "Столик занят" } }]) {
    await assert.rejects(readApiResponse(Response.json(payload, { status: 409 }), "Ошибка"), /Столик занят.*HTTP 409/);
  }
});

test("restaurant malformed and empty success bodies never become successful saves", async () => {
  for (const body of ["", "not-json", "<html>Login</html>"]) {
    await assert.rejects(readApiResponse(new Response(body), "Ошибка"), /некорректный ответ.*HTTP 200/);
  }
});

test("restaurant valid JSON responses and explicit no-content responses remain supported", async () => {
  assert.deepEqual(await readApiResponse(Response.json({ id: 17 }), "Ошибка"), { id: 17 });
  assert.deepEqual(await readApiResponse(Response.json([{ id: 17 }]), "Ошибка"), [{ id: 17 }]);
  assert.equal(await readApiResponse(new Response(null, { status: 204 }), "Ошибка"), null);
});

test("restaurant non-object errors use a meaningful fallback and HTTP status", async () => {
  for (const payload of [null, [], "failure", { message: "" }]) {
    await assert.rejects(readApiResponse(Response.json(payload, { status: 500 }), "Не удалось выполнить действие"), /Не удалось выполнить действие.*HTTP 500/);
  }
});

test("restaurant response read errors are not hidden as a successful response", async () => {
  const response = { status: 200, text: async () => { throw new Error("connection interrupted"); } };
  await assert.rejects(readApiResponse(response, "Ошибка"), /connection interrupted/);
});

test("overnight table occupancy appears on both calendar dates", () => {
  const segment = { starts_at: "2026-11-03T23:30:00+05:00", ends_at: "2026-11-04T01:30:00+05:00", is_extension: false };
  const result = restaurantCalendarSegments([segment]);
  assert.deepEqual(result.map((item) => item.starts_at.slice(0, 16)), ["2026-11-03T23:30", "2026-11-04T00:00"]);
  assert.equal(Date.parse(result[0].ends_at), Date.parse(result[1].starts_at));
  assert.equal(result[1].ends_at, segment.ends_at);
  assert.ok(result.every((item) => item.is_extension === false));
});

test("overnight renewals keep their extension label and same-day segments stay unchanged", () => {
  const renewal = { starts_at: "2026-11-03T23:00:00+05:00", ends_at: "2026-11-04T01:00:00+05:00", is_extension: true };
  assert.ok(restaurantCalendarSegments([renewal]).every((item) => item.is_extension));
  const ordinary = { ...renewal, starts_at: "2026-11-03T21:00:00+05:00", ends_at: "2026-11-03T23:00:00+05:00" };
  assert.deepEqual(restaurantCalendarSegments([ordinary]), [ordinary]);
});

test("invalid restaurant calendar timestamps fail explicitly", () => {
  assert.throws(() => restaurantCalendarSegments([{ starts_at: "invalid", ends_at: "invalid", is_extension: false }]), /Некорректное время/);
});

test("choosing the first time fills every visit without changing dates", () => {
  const visits = [{ date: "2026-11-03", time: "" }, { date: "2026-11-05", time: "" }, { date: "2026-11-07", time: "" }];
  const result = changeVisitTime(visits, 0, "15:00");
  assert.deepEqual(result.map((visit) => visit.time), ["15:00", "15:00", "15:00"]);
  assert.deepEqual(result.map((visit) => visit.date), visits.map((visit) => visit.date));
});

test("first selection in any empty visit populates the other dates", () => {
  assert.deepEqual(changeVisitTime([{ date: "a", time: "" }, { date: "b", time: "" }], 1, "12:15").map((visit) => visit.time), ["12:15", "12:15"]);
});

test("changing a later lesson does not change the others", () => {
  const visits = [{ date: "a", time: "15:00" }, { date: "b", time: "15:00" }, { date: "c", time: "15:00" }];
  assert.deepEqual(changeVisitTime(visits, 1, "16:00").map((visit) => visit.time), ["15:00", "16:00", "15:00"]);
});

test("changing common time preserves individually edited visits", () => {
  const visits = changeVisitTime([{ date: "a", time: "15:00" }, { date: "b", time: "15:00" }, { date: "c", time: "15:00" }], 1, "16:00");
  assert.deepEqual(applyDefaultVisitTime(visits, "14:30").map((visit) => visit.time), ["14:30", "16:00", "14:30"]);
  assert.deepEqual(applyDefaultVisitTime(visits, "").map((visit) => visit.time), ["15:00", "16:00", "15:00"]);
});

test("reselecting the same later time does not create a manual exception", () => {
  const visits = [{ date: "a", time: "11:00" }, { date: "b", time: "11:00" }, { date: "c", time: "11:00" }];
  const unchanged = changeVisitTime(visits, 2, "11:00");
  assert.deepEqual(changeVisitTime(unchanged, 0, "13:00").map((visit) => visit.time), ["13:00", "13:00", "13:00"]);
});

test("schedule navigation retains the exact day and specialist", () => {
  const href = scheduleHref("2026-11-03", "17");
  assert.equal(scheduleReturnHref(new URLSearchParams({ return_to: href }).toString()), href);
  const date = validScheduleDate(new URL(href, "https://schedule.local").searchParams.get("date"));
  assert.equal(date.getFullYear(), 2026);
  assert.equal(date.getMonth(), 10);
  assert.equal(date.getDate(), 3);
});

test("schedule restore rejects impossible dates and external return links", () => {
  for (const value of ["2026-02-30", "invalid", "2026-13-01", null]) assert.equal(validScheduleDate(value), null);
  for (const value of ["https://evil.example/", "//evil.example/", "javascript:alert(1)", "http://["]) {
    assert.equal(scheduleReturnHref(new URLSearchParams({ return_to: value }).toString()), "/partner/dashboard/schedule");
  }
});

test("cancelled and no-show records are hidden without hiding completed history", () => {
  for (const status of ["cancelled", "canceled", "no_show", "missed", "Неявка"]) assert.equal(calendarBookingVisible(status), false);
  for (const status of ["booked", "arrived", "completed"]) assert.equal(calendarBookingVisible(status), true);
});

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

test("booking request IDs work without the secure-context randomUUID API", () => {
  const source = { getRandomValues: (bytes) => bytes.fill(255) };
  assert.equal(source.randomUUID, undefined);
  const { createRequestId } = loadSource(path.join("lib", "requestId.ts"), source);
  assert.equal(createRequestId(), "ffffffff-ffff-4fff-bfff-ffffffffffff");
});

test("booking request IDs are unique RFC 4122 version 4 UUIDs", () => {
  const ids = Array.from({ length: 100 }, () => createRequestId());
  assert.equal(new Set(ids).size, ids.length);
  for (const id of ids) assert.match(id, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
});

test("unsupported random generation produces an explicit error, not a weak fallback", () => {
  const { createRequestId } = loadSource(path.join("lib", "requestId.ts"), {});
  assert.throws(createRequestId, /Браузер не поддерживает создание идентификатора записи/);
});
