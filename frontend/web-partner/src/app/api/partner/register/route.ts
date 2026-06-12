import { NextResponse } from "next/server";

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || "http://127.0.0.1:8000";
const RU_PHONE_RE = /^\+7\d{10}$/;

function normalizeRuPhone(rawPhone: string): string {
  return rawPhone.replace(/[\s\-()]/g, "");
}

export async function POST(request: Request) {
  const body = (await request.json()) as {
    login?: string;
    password?: string;
    acceptedOffer?: boolean;
    full_name?: string;
    phone?: string;
    company_name?: string;
    business_category?: string;
    address?: string;
  };

  const login = (body.login || "").trim();
  const password = (body.password || "").trim();
  const acceptedOffer = Boolean(body.acceptedOffer);
  const fullName = (body.full_name || "").trim() || login;
  const phone = normalizeRuPhone((body.phone || "").trim() || "+7");
  const companyName = (body.company_name || "").trim();
  const businessCategory = (body.business_category || "").trim();
  const address = (body.address || "").trim();

  if (!acceptedOffer) {
    return NextResponse.json(
      { message: "Нужно принять условия договора оферты" },
      { status: 400 },
    );
  }

  if (!login || !password) {
    return NextResponse.json({ message: "Логин и пароль обязательны" }, { status: 400 });
  }

  if (password.length < 6) {
    return NextResponse.json(
      { message: "Пароль должен содержать минимум 6 символов" },
      { status: 400 },
    );
  }

  if (!RU_PHONE_RE.test(phone)) {
    return NextResponse.json(
      { message: "Телефон должен быть в формате +7XXXXXXXXXX" },
      { status: 400 },
    );
  }

  try {
    const response = await fetch(`${BACKEND_BASE_URL}/api/v1/common/auth/register/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        full_name: fullName,
        phone,
        email: login,
        password,
        user_type: "partner",
        company_name: companyName,
        business_category: businessCategory,
        address,
      }),
      cache: "no-store",
    });

    const payload = await response.json();
    if (!response.ok) {
      return NextResponse.json(
        { message: payload.message || "Не удалось завершить регистрацию" },
        { status: response.status },
      );
    }

    return NextResponse.json({ ok: true, user: { name: login } }, { status: 201 });
  } catch {
    return NextResponse.json({ message: "Backend API недоступен" }, { status: 503 });
  }
}
