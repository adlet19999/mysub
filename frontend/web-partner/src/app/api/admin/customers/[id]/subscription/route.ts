import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || "http://127.0.0.1:8000";
const SESSION_COOKIE = "mysub_admin_session";

type RouteContext = { params: { id: string } };

export async function POST(request: Request, { params }: RouteContext) {
  const token = cookies().get(SESSION_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ message: "Требуется вход" }, { status: 401 });
  }

  try {
    const response = await fetch(`${BACKEND_BASE_URL}/api/v1/common/admin/customers/${params.id}/subscription/`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(await request.json()),
      cache: "no-store",
    });
    const payload = await response.json();
    if (!response.ok) {
      const result = NextResponse.json({ message: payload.message || "Не удалось обновить подписку" }, { status: response.status });
      if (response.status === 401) result.cookies.delete(SESSION_COOKIE);
      return result;
    }
    return NextResponse.json(payload);
  } catch {
    return NextResponse.json({ message: "Backend API недоступен" }, { status: 503 });
  }
}