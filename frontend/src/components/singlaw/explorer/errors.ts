import { ApiError } from "@/lib/api";

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  // A non-JSON body (e.g. the SPA shell from a missing route) surfaces as a parse error.
  if (error instanceof SyntaxError)
    return "SingLaw returned an unexpected response. Please try again.";
  if (error instanceof Error && error.message) return error.message;
  return "Something went wrong on our end.";
}

export function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}
