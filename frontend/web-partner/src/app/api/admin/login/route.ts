import { NextResponse } from "next/server";

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || "http://127.0.0.1:8000";
const SESSION_COOKIE = "mysub_admin_session";

export async function POST(request: Request) {
  const body = (await request.json()) as { username?: string; password?: string };
  const username = (body.username || "").trim();
  const password = body.password || "";

  if (!username || !password) {
    return NextResponse.json({ message: "Логин и пароль обязательны" }, { status: 400 });
  }

  try {
    const response = await fetch(`${BACKEND_BASE_URL}/api/v1/common/admin/login/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
      cache: "no-store",
    });
    const payload = await response.json();
    if (!response.ok) {
      return NextResponse.json({ message: payload.message || "Ошибка входа" }, { status: response.status });
    }

    const result = NextResponse.json({ admin: payload.admin });
    result.cookies.set(SESSION_COOKIE, payload.token, {
      httpOnly: true,
      sameSite: "lax",
      secure: request.headers.get("x-forwarded-proto") === "https",
      maxAge: 60 * 60 * 8,
      path: "/",
    });
    return result;
  } catch {
    return NextResponse.json({ message: "Backend API недоступен" }, { status: 503 });
  }
}