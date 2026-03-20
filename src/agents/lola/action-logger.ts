export function logAction(action: string, payload: Record<string, unknown>) {
  const redacted = { ...payload };
  if ("subject" in redacted) {
    redacted.subject = "[redacted]";
  }
  if ("sender" in redacted) {
    redacted.sender = "[redacted]";
  }
  console.log(`ACTION:${action} ${JSON.stringify(redacted)}`);
  return true;
}
