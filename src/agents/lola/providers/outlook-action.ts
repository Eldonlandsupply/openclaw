export type OutlookSendDraftPayload = {
  draftId: string;
  subject: string;
  to: string[];
  body: string;
};

export type OutlookActionResult = {
  ok: true;
  provider: "Outlook";
  externalRef: string;
  dryRun?: boolean;
};

export class OutlookActionProvider {
  async sendDraft(payload: OutlookSendDraftPayload, dryRun: boolean): Promise<OutlookActionResult> {
    return {
      ok: true,
      provider: "Outlook",
      externalRef: dryRun ? `dryrun:${payload.draftId}` : `outlook:${payload.draftId}`,
      dryRun,
    };
  }
}
