export const RU_PHONE_RE = /^\+7\d{10}$/;

export function normalizeRuPhone(rawPhone: string): string {
  const digits = (rawPhone || "").replace(/\D/g, "");
  if (!digits) {
    return "+7";
  }

  let normalizedDigits = digits;
  if (normalizedDigits.startsWith("8")) {
    normalizedDigits = `7${normalizedDigits.slice(1)}`;
  }
  if (!normalizedDigits.startsWith("7")) {
    normalizedDigits = `7${normalizedDigits}`;
  }

  return `+${normalizedDigits.slice(0, 11)}`;
}

export function formatRuPhone(rawPhone: string): string {
  const normalized = normalizeRuPhone(rawPhone);
  const digits = normalized.replace(/\D/g, "").slice(1);

  const code = digits.slice(0, 3);
  const first = digits.slice(3, 6);
  const second = digits.slice(6, 8);
  const third = digits.slice(8, 10);

  let result = "+7";
  if (code) {
    result += ` (${code}`;
    if (code.length === 3) {
      result += ")";
    }
  }
  if (first) {
    result += ` ${first}`;
  }
  if (second) {
    result += `-${second}`;
  }
  if (third) {
    result += `-${third}`;
  }

  return result;
}

export function isValidRuPhone(rawPhone: string): boolean {
  return RU_PHONE_RE.test(normalizeRuPhone(rawPhone));
}
