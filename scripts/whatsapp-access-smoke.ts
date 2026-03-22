import { checkInboundAccessControl } from "../src/web/inbound/access-control.js";

type Args = {
  accountId: string;
  from: string;
  remoteJid: string;
  senderE164?: string;
  selfE164?: string;
  group: boolean;
  fromMe: boolean;
};

function usage(): never {
  console.error(
    [
      "Usage:",
      "  bun scripts/whatsapp-access-smoke.ts --from <+15551234567|jid> [--account <id>] [--group] [--sender <+1555...>] [--self <+1555...>] [--from-me]",
      "",
      "Examples:",
      "  bun scripts/whatsapp-access-smoke.ts --account work --from +15551230000",
      "  bun scripts/whatsapp-access-smoke.ts --account work --group --from 1203630@g.us --sender +15551230000",
    ].join("\n"),
  );
  process.exit(1);
}

function parseArgs(argv: string[]): Args {
  const parsed: Args = {
    accountId: "default",
    from: "",
    remoteJid: "",
    group: false,
    fromMe: false,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];
    switch (arg) {
      case "--account":
        parsed.accountId = next ?? usage();
        i += 1;
        break;
      case "--from":
        parsed.from = next ?? usage();
        i += 1;
        break;
      case "--sender":
        parsed.senderE164 = next ?? usage();
        i += 1;
        break;
      case "--self":
        parsed.selfE164 = next ?? usage();
        i += 1;
        break;
      case "--group":
        parsed.group = true;
        break;
      case "--from-me":
        parsed.fromMe = true;
        break;
      default:
        usage();
    }
  }

  if (!parsed.from) {
    usage();
  }

  parsed.remoteJid = parsed.from.includes("@")
    ? parsed.from
    : parsed.group
      ? parsed.from
      : `${parsed.from.replace(/^\+/, "")}@s.whatsapp.net`;

  return parsed;
}

const args = parseArgs(process.argv.slice(2));

const result = await checkInboundAccessControl({
  accountId: args.accountId,
  from: args.from,
  selfE164: args.selfE164 ?? null,
  senderE164: args.senderE164 ?? null,
  group: args.group,
  pushName: undefined,
  isFromMe: args.fromMe,
  sock: {
    sendMessage: async () => ({ ok: true }),
  },
  remoteJid: args.remoteJid,
});

console.log(
  JSON.stringify(
    {
      input: args,
      result,
    },
    null,
    2,
  ),
);
