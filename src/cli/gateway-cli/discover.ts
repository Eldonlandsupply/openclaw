import {
  resolveGatewayDiscoveryEndpoint,
  type GatewayBonjourBeacon,
} from "../../infra/bonjour-discovery.js";
import { colorize, theme } from "../../terminal/theme.js";

export type GatewayDiscoverOpts = {
  timeout?: string;
  json?: boolean;
};

export function parseDiscoverTimeoutMs(raw: unknown, fallbackMs: number): number {
  if (raw === undefined || raw === null) {
    return fallbackMs;
  }
  const value =
    typeof raw === "string"
      ? raw.trim()
      : typeof raw === "number" || typeof raw === "bigint"
        ? String(raw)
        : null;
  if (value === null) {
    throw new Error("invalid --timeout");
  }
  if (!value) {
    return fallbackMs;
  }
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    throw new Error(`invalid --timeout: ${value}`);
  }
  return parsed;
}

export function pickBeaconHost(beacon: GatewayBonjourBeacon): string | null {
  return resolveGatewayDiscoveryEndpoint(beacon)?.host ?? null;
}

export function pickGatewayPort(beacon: GatewayBonjourBeacon): number | null {
  return resolveGatewayDiscoveryEndpoint(beacon)?.port ?? null;
}

export function dedupeBeacons(beacons: GatewayBonjourBeacon[]): GatewayBonjourBeacon[] {
  const out: GatewayBonjourBeacon[] = [];
  const seen = new Set<string>();
  for (const b of beacons) {
    const host = pickBeaconHost(b) ?? "";
    const key = [
      b.domain ?? "",
      b.instanceName ?? "",
      b.displayName ?? "",
      host,
      String(b.port ?? ""),
      String(b.gatewayPort ?? ""),
    ].join("|");
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    out.push(b);
  }
  return out;
}

export function renderBeaconLines(beacon: GatewayBonjourBeacon, rich: boolean): string[] {
  const nameRaw = (beacon.displayName || beacon.instanceName || "Gateway").trim();
  const domainRaw = (beacon.domain || "local.").trim();

  const title = colorize(rich, theme.accentBright, nameRaw);
  const domain = colorize(rich, theme.muted, domainRaw);

  const endpoint = resolveGatewayDiscoveryEndpoint(beacon);

  const lines = [`- ${title} ${domain}`];

  if (beacon.tailnetDns) {
    lines.push(`  ${colorize(rich, theme.info, "tailnet")}: ${beacon.tailnetDns}`);
  }
  if (beacon.lanHost) {
    lines.push(`  ${colorize(rich, theme.info, "lan")}: ${beacon.lanHost}`);
  }
  if (beacon.host) {
    lines.push(`  ${colorize(rich, theme.info, "host")}: ${beacon.host}`);
  }

  if (endpoint) {
    lines.push(
      `  ${colorize(rich, theme.muted, "ws")}: ${colorize(rich, theme.command, endpoint.wsUrl)}`,
    );
  }
  if (beacon.role) {
    lines.push(`  ${colorize(rich, theme.muted, "role")}: ${beacon.role}`);
  }
  if (beacon.transport) {
    lines.push(`  ${colorize(rich, theme.muted, "transport")}: ${beacon.transport}`);
  }
  if (beacon.gatewayTls) {
    const fingerprint = beacon.gatewayTlsFingerprintSha256
      ? `sha256 ${beacon.gatewayTlsFingerprintSha256}`
      : "enabled";
    lines.push(`  ${colorize(rich, theme.muted, "tls")}: ${fingerprint}`);
  }
  if (typeof beacon.sshPort === "number" && beacon.sshPort > 0 && endpoint) {
    const ssh = `ssh -N -L 18789:127.0.0.1:18789 <user>@${endpoint.host} -p ${beacon.sshPort}`;
    lines.push(`  ${colorize(rich, theme.muted, "ssh")}: ${colorize(rich, theme.command, ssh)}`);
  }
  return lines;
}
