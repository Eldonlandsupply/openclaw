import { describe, expect, it } from "vitest";
import { summarizeCmsTask, type CmsTaskPayload } from "./cms-task.js";

describe("summarizeCmsTask", () => {
  it("extracts hero image + markup doc from a CMS payload", () => {
    const payload: CmsTaskPayload = {
      task_id: "task_20260312_website_001",
      request_summary: "Update homepage content and hero image",
      attachments: [
        {
          attachment_id: "att_hero_001",
          filename: "homepage-markup.pdf",
          content_type: "application/pdf",
          size_bytes: 100,
        },
        {
          attachment_id: "att_hero_002",
          filename: "new-hero.webp",
          content_type: "image/webp",
          size_bytes: 100,
        },
      ],
      storage_links: [
        { provider: "s3", url: "s3://openclaw-inbox/incoming/homepage-markup.pdf" },
        { provider: "foo", url: "ftp://example.com/file.pdf" },
      ],
    };

    const audit = summarizeCmsTask(payload);
    expect(audit.taskId).toBe("task_20260312_website_001");
    expect(audit.heroImage?.filename).toBe("new-hero.webp");
    expect(audit.markupDoc?.filename).toBe("homepage-markup.pdf");
    expect(audit.unsupportedStorageLinks).toEqual([
      { provider: "foo", url: "ftp://example.com/file.pdf" },
    ]);
  });
});
