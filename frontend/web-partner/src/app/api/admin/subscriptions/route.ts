import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || "http://127.0.0.1:8000";
const SESSION_COOKIE = "mysub_admin_session";

async function proxy(request: Request, method: "GET" | "POST") {
  const token = cookies().get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ message: "Требуется вход" }, { status: 401 });
  try {
    const response = await fetch(`${BACKEND_BASE_URL}/api/v1/common/admin/subscriptions/`, {
      method,
      headers: { Authorization: `Bearer ${token}`, ...(method === "POST" ? { "Content-Type": "application/json" } : {}) },
      ...(method === "POST" ? { body: JSON.stringify(await request.json()) } : {}),
      cache: "no-store",
    });
    const payload = await response.json();
    const result = NextResponse.json(payload, { status: response.status });
    if (response.status === 401) result.cookies.delete(SESSION_COOKIE);
    return result;
  } catch {
    return NextResponse.json({ message: "Backend API недоступен" }, { status: 503 });
  }
}

export function GET(request: Request) { return proxy(request, "GET"); }
export function POST(request: Request) { return proxy(request, "POST"); }