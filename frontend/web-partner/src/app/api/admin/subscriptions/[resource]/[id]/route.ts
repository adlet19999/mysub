import { cookies } from "next/headers";
import { NextResponse } from "next/server";

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || "http://127.0.0.1:8000";
const SESSION_COOKIE = "mysub_admin_session";

export async function PATCH(request: Request, { params }: { params: { resource: string; id: string } }) {
  const token = cookies().get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ message: "Требуется вход" }, { status: 401 });
  try {
    const response = await fetch(`${BACKEND_BASE_URL}/api/v1/common/admin/subscriptions/${params.resource}/${params.id}/`, {
      method: "PATCH",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(await request.json()),
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