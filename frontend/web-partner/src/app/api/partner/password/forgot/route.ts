import { NextResponse } from "next/server";

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || "http://127.0.0.1:8000";

export async function POST(request: Request) {
  const body = (await request.json()) as { email?: string };
  const email = (body.email || "").trim().toLowerCase();

  if (!email) {
    return NextResponse.json({ message: "Email обязателен" }, { status: 400 });
  }

  try {
    const response = await fetch(`${BACKEND_BASE_URL}/api/v1/common/auth/forgot-password/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
      cache: "no-store",
    });

    const payload = await response.json();
    return NextResponse.json(payload, { status: response.status });
  } catch {
    return NextResponse.json({ message: "Backend API недоступен" }, { status: 503 });
  }
}
