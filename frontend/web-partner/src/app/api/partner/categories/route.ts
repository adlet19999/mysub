import { NextResponse } from "next/server";

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL || "http://127.0.0.1:8000";

export async function GET() {
  try {
    const response = await fetch(`${BACKEND_BASE_URL}/api/v1/common/business-categories/`, { cache: "no-store" });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ message: "Не удалось загрузить категории" }, { status: 503 });
  }
}