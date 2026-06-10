import { NextResponse } from "next/server";

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || "http://127.0.0.1:8000";
const TENANT = process.env.NEXT_PUBLIC_TENANT_SLUG || "public";

type Params = { params: Promise<{ id: string }> };

export async function PATCH(request: Request, { params }: Params) {
  const { id } = await params;
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
    const response = await fetch(`${BACKEND_BASE_URL}/api/v1/partner/bookings/${id}/`, {
      method: "PATCH",
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
        client_phone: (body.clientPhone || "").trim(),
        status: (body.status || "booked").trim(),
      }),
      cache: "no-store",
    });

    const payload = await response.json();
    if (!response.ok) {
      return NextResponse.json(
        { message: payload?.detail || payload?.message || "Ошибка обновления записи" },
        { status: response.status },
      );
    }

    return NextResponse.json({ ok: true, item: payload });
  } catch {
    return NextResponse.json({ message: "Backend API недоступен" }, { status: 503 });
  }
}
