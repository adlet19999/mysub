import { NextResponse } from "next/server";

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || "http://127.0.0.1:8000";

type ResetBody = {
	email?: string;
  currentPassword?: string;
  uid?: string;
  token?: string;
  newPassword?: string;
};

export async function POST(request: Request) {
  const body = (await request.json()) as ResetBody;
	const email = (body.email || "").trim();
  const currentPassword = body.currentPassword || "";
  const uid = (body.uid || "").trim();
  const token = (body.token || "").trim();
  const newPassword = body.newPassword || "";

  if (email && currentPassword && newPassword) {
    const response = await fetch(`${BACKEND_BASE_URL}/api/v1/common/auth/initial-password-change/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, current_password: currentPassword, new_password: newPassword }),
      cache: "no-store",
    });
    const payload = await response.json();
    return NextResponse.json(payload, { status: response.status });
  }

  if (!uid || !token || !newPassword) {
    return NextResponse.json({ message: "uid, token и новый пароль обязательны" }, { status: 400 });
  }

  try {
    const response = await fetch(`${BACKEND_BASE_URL}/api/v1/common/auth/reset-password/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ uid, token, new_password: newPassword }),
      cache: "no-store",
    });

    const payload = await response.json();
    return NextResponse.json(payload, { status: response.status });
  } catch {
    return NextResponse.json({ message: "Backend API недоступен" }, { status: 503 });
  }
}
