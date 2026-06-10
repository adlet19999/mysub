import { NextResponse } from "next/server";

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || "http://127.0.0.1:8000";
const TENANT = process.env.NEXT_PUBLIC_TENANT_SLUG || "public";

export async function GET(request: Request) {
  const partnerEmail = (request.headers.get("x-partner-email") || "").trim().toLowerCase();
  const partnerCategory = (request.headers.get("x-partner-category") || "").trim();

  try {
    const response = await fetch(`${BACKEND_BASE_URL}/api/v1/partner/services/`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        "X-Tenant": TENANT,
        ...(partnerEmail ? { "X-Partner-Email": partnerEmail } : {}),
        ...(partnerCategory ? { "X-Partner-Category": partnerCategory } : {}),
      },
      cache: "no-store",
    });

    const payload = await response.json();
    if (!response.ok) {
      return NextResponse.json(
        { message: payload?.detail || payload?.message || "Ошибка получения услуг" },
        { status: response.status },
      );
    }

    return NextResponse.json(Array.isArray(payload) ? payload : []);
  } catch {
    return NextResponse.json({ message: "Backend API недоступен" }, { status: 503 });
  }
}
