export type GraphSubscriptionRequest = {
  changeType: string;
  notificationUrl: string;
  resource: string;
  expirationDateTime: string;
  clientState?: string;
  includeResourceData?: boolean;
};

export type BuildGraphSubscriptionOptions = {
  resource: string;
  notificationUrl: string;
  changeType?: string;
  expiresInMinutes?: number;
  clientState?: string;
  includeResourceData?: boolean;
};

const DEFAULT_EXPIRY_MINUTES = 60;

export function buildGraphSubscriptionRequest(
  options: BuildGraphSubscriptionOptions,
  now = new Date(),
): GraphSubscriptionRequest {
  const resource = options.resource.trim();
  const notificationUrl = options.notificationUrl.trim();
  if (!resource) {
    throw new Error("resource is required");
  }
  if (!notificationUrl) {
    throw new Error("notificationUrl is required");
  }
  const expiresInMinutes =
    typeof options.expiresInMinutes === "number" && options.expiresInMinutes > 0
      ? Math.floor(options.expiresInMinutes)
      : DEFAULT_EXPIRY_MINUTES;
  const expirationDateTime = new Date(now.getTime() + expiresInMinutes * 60_000).toISOString();

  return {
    changeType: options.changeType?.trim() || "created,updated",
    notificationUrl,
    resource,
    expirationDateTime,
    clientState: options.clientState?.trim() || undefined,
    includeResourceData: options.includeResourceData === true ? true : undefined,
  };
}

export function nextGraphSubscriptionRenewalDate(
  expirationDateTime: string,
  renewBeforeMinutes = 15,
): Date {
  const expiry = new Date(expirationDateTime);
  if (Number.isNaN(expiry.getTime())) {
    throw new Error("Invalid expirationDateTime");
  }
  return new Date(expiry.getTime() - Math.max(1, renewBeforeMinutes) * 60_000);
}
