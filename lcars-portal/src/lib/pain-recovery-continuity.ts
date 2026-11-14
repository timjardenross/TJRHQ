export type ContinuityContext = {
  source: "activity" | "learning" | "guide";
  label: string;
  returnPath: string;
  step?: number;
  total?: number;
};

export function contextHref(path: string, context: ContinuityContext): string {
  const params = new URLSearchParams({
    from: context.source,
    context: context.label,
    returnTo: context.returnPath,
  });
  if (typeof context.step === "number")
    params.set("step", String(context.step));
  if (typeof context.total === "number")
    params.set("total", String(context.total));
  return `${path}${path.includes("?") ? "&" : "?"}${params.toString()}`;
}

export function parseStep(value: string | null, total: number): number {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 0) return 0;
  return Math.min(parsed, Math.max(0, total - 1));
}

export function continuityCopy(
  context: Pick<ContinuityContext, "source" | "label">,
): string {
  if (context.source === "activity")
    return `Returning from ${context.label}. You can resume, choose another route or stop.`;
  if (context.source === "learning")
    return `Returning from ${context.label}. Continue from where you left off, or choose something else.`;
  return `Returning from ${context.label}. Nothing needs to be repeated.`;
}
