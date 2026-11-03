export async function readApiResponse(response: Response, errorMessage: string): Promise<unknown> {
  if (response.status === 204) return null;
  const text = await response.text();
  let payload: unknown;
  try {
    payload = JSON.parse(text);
  } catch (error) {
    if (!(error instanceof SyntaxError)) throw error;
    throw new Error(`${errorMessage}. Сервер вернул некорректный ответ (HTTP ${response.status}). Повторите попытку; если ошибка сохраняется, обратитесь к администратору.`);
  }
  if (!response.ok) {
    let message = errorMessage;
    if (payload && typeof payload === "object") {
      if ("message" in payload && typeof payload.message === "string" && payload.message.trim()) message = payload.message;
      else if ("detail" in payload && typeof payload.detail === "string" && payload.detail.trim()) message = payload.detail;
      else if ("error" in payload && payload.error && typeof payload.error === "object"
        && "message" in payload.error && typeof payload.error.message === "string" && payload.error.message.trim()) message = payload.error.message;
    }
    throw new Error(`${message} (HTTP ${response.status})`);
  }
  return payload;
}
