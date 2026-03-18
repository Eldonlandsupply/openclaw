import { loadProviderUsageSummary as loadProviderUsageSummaryFresh } from "./provider-usage.load.js";

export {
  formatUsageReportLines,
  formatUsageSummaryLine,
  formatUsageWindowSummary,
} from "./provider-usage.format.js";
export { resolveUsageProviderId } from "./provider-usage.shared.js";
export type {
  ProviderUsageSnapshot,
  UsageProviderId,
  UsageSummary,
  UsageWindow,
} from "./provider-usage.types.js";

const PROVIDER_USAGE_CACHE_TTL_MS = 30_000;

type UsageSummaryOptions = Parameters<typeof loadProviderUsageSummaryFresh>[0];
type CachedUsageEntry = {
  summary?: Awaited<ReturnType<typeof loadProviderUsageSummaryFresh>>;
  updatedAt?: number;
  inFlight?: Promise<Awaited<ReturnType<typeof loadProviderUsageSummaryFresh>>>;
};

const providerUsageCache = new Map<string, CachedUsageEntry>();

function getProviderUsageCacheKey(opts: UsageSummaryOptions = {}): string | null {
  if (opts.fetch || opts.auth || opts.agentDir) {
    return null;
  }
  const providers = opts.providers ? opts.providers.toSorted() : [];
  return JSON.stringify({
    providers,
    timeoutMs: opts.timeoutMs ?? null,
  });
}

export async function loadProviderUsageSummary(
  opts: UsageSummaryOptions = {},
): Promise<Awaited<ReturnType<typeof loadProviderUsageSummaryFresh>>> {
  const cacheKey = getProviderUsageCacheKey(opts);
  if (!cacheKey) {
    return await loadProviderUsageSummaryFresh(opts);
  }

  const now = Date.now();
  const cached = providerUsageCache.get(cacheKey);
  if (cached?.summary && cached.updatedAt && now - cached.updatedAt < PROVIDER_USAGE_CACHE_TTL_MS) {
    return cached.summary;
  }
  if (cached?.inFlight) {
    return await cached.inFlight;
  }

  const entry: CachedUsageEntry = cached ?? {};
  const inFlight = loadProviderUsageSummaryFresh(opts)
    .then((summary) => {
      providerUsageCache.set(cacheKey, { summary, updatedAt: Date.now() });
      return summary;
    })
    .catch((error) => {
      if (entry.summary) {
        return entry.summary;
      }
      throw error;
    })
    .finally(() => {
      const current = providerUsageCache.get(cacheKey);
      if (current?.inFlight === inFlight) {
        current.inFlight = undefined;
        providerUsageCache.set(cacheKey, current);
      }
    });

  entry.inFlight = inFlight;
  providerUsageCache.set(cacheKey, entry);
  return await inFlight;
}

export const __test = {
  getProviderUsageCacheKey,
  providerUsageCache,
  PROVIDER_USAGE_CACHE_TTL_MS,
  loadProviderUsageSummaryFresh,
};
