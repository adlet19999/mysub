import { NextResponse } from "next/server";
const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || "http://127.0.0.1:8000";
const TENANT = process.env.NEXT_PUBLIC_TENANT_SLUG || "public";

export async function GET(request: Request) {
  const partnerEmail = (request.headers.get("x-partner-email") || "").trim().toLowerCase();

  try {
    const response = await fetch(`${BACKEND_BASE_URL}/api/v1/partner/bookings/`, {
      method: "GET",
      headers: {
        "Content-Type": "application/json",
        "X-Tenant": TENANT,
        ...(partnerEmail ? { "X-Partner-Email": partnerEmail } : {}),
      },
      cache: "no-store",
    });

    const payload = await response.json();
    if (!response.ok) {
      return NextResponse.json(
        { message: payload?.detail || "Ошибка получения записей" },
        { status: response.status },
      );
    }

    return NextResponse.json({ items: Array.isArray(payload) ? payload : [] });
  } catch {
    return NextResponse.json({ message: "Backend API недоступен" }, { status: 503 });
  }
}

export async function POST(request: Request) {
  const partnerEmail = (request.headers.get("x-partner-email") || "").trim().toLowerCase();
  const body = (await request.json()) as {
    specialist?: string;
    service?: string;
    clientName?: string;
    clientPhone?: string;
    startTime?: string;
    status?: string;
  };

  try {
    const response = await fetch(`${BACKEND_BASE_URL}/api/v1/partner/bookings/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Tenant": TENANT,
        ...(partnerEmail ? { "X-Partner-Email": partnerEmail } : {}),
      },
      body: JSON.stringify({
        service_name: (body.service || "").trim(),
        manager_name: (body.specialist || "").trim(),
        starts_at: (body.startTime || "").trim(),
        client_name: (body.clientName || "").trim(),
        client_phone: (body.clientPhone || "").trim() || "+7",
        status: (body.status || "booked").trim(),
      }),
      cache: "no-store",
    });

    const payload = await response.json();
    if (!response.ok) {
      return NextResponse.json(
        { message: payload?.detail || payload?.message || "Ошибка создания записи" },
        { status: response.status },
      );
    }

    return NextResponse.json({ ok: true, item: payload }, { status: 201 });
  } catch {
    return NextResponse.json({ message: "Backend API недоступен" }, { status: 503 });
  }
}
