import type { StocksPayload } from "../types";

export class StocksApiError extends Error {
  constructor(message: string, readonly status?: number) {
    super(message);
    this.name = "StocksApiError";
  }
}

export async function fetchStocks(signal?: AbortSignal): Promise<StocksPayload> {
  return requestStocks("/api/stocks", { method: "GET", signal });
}

export async function screenStocks(criteria: unknown, signal?: AbortSignal): Promise<StocksPayload> {
  return requestStocks("/api/screen", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ criteria }),
    signal,
  });
}

async function requestStocks(path: string, options: RequestInit): Promise<StocksPayload> {
  const response = await fetch(path, {
    ...options,
    headers: { Accept: "application/json", ...options.headers },
    cache: "no-store",
  });
  if (!response.ok) {
    let message = `Stock API request failed (${response.status}).`;
    try {
      const error = await response.json() as { error?: unknown };
      if (typeof error.error === "string") message = error.error;
    } catch {
      // Retain the status-based error when the response is not JSON.
    }
    throw new StocksApiError(message, response.status);
  }
  const payload: unknown = await response.json();
  if (
    !payload ||
    typeof payload !== "object" ||
    typeof (payload as StocksPayload).demo !== "boolean" ||
    !Array.isArray((payload as StocksPayload).stocks)
  ) {
    throw new StocksApiError("Stock API returned an invalid response.");
  }
  return payload as StocksPayload;
}
