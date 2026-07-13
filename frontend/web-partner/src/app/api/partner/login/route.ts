import { NextResponse } from "next/server";

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || "http://127.0.0.1:8000";

export async function POST(request: Request) {
  const body = (await request.json()) as { login?: string; password?: string };
  const login = (body.login || "").trim();
  const password = (body.password || "").trim();

  if (!login || !password) {
    return NextResponse.json({ message: "Логин и пароль обязательны" }, { status: 400 });
  }

  try {
    const response = await fetch(`${BACKEND_BASE_URL}/api/v1/common/auth/login/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: login, password }),
      cache: "no-store",
    });
    const payload = await response.json();

    if (!response.ok) {
      return NextResponse.json(
        { message: payload.message || "Ошибка авторизации" },
        { status: response.status },
      );
    }

    const userType = payload?.user?.user_type;
    if (userType !== "partner" && userType !== "manager") {
      return NextResponse.json({ message: "Роль пользователя не поддерживается" }, { status: 403 });
    }

    return NextResponse.json({ ok: true, user: payload.user });
  } catch {
    return NextResponse.json({ message: "Backend API недоступен" }, { status: 503 });
  }
}
