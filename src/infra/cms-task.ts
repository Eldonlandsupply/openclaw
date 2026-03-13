export type CmsTaskAttachment = {
  attachment_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  checksum?: string;
};

export type CmsTaskStorageLink = {
  provider: string;
  bucket?: string;
  object_key?: string;
  url: string;
};

export type CmsTaskPayload = {
  task_id: string;
  source?: string;
  request_summary?: string;
  target_system?: string;
  attachments?: CmsTaskAttachment[];
  storage_links?: CmsTaskStorageLink[];
};

export type CmsTaskAudit = {
  taskId: string;
  summary: string;
  heroImage?: CmsTaskAttachment;
  markupDoc?: CmsTaskAttachment;
  unsupportedStorageLinks: CmsTaskStorageLink[];
};

function isSupportedStorageUrl(url: string): boolean {
  return url.startsWith("https://") || url.startsWith("http://") || url.startsWith("s3://");
}

export function summarizeCmsTask(payload: CmsTaskPayload): CmsTaskAudit {
  const attachments = payload.attachments ?? [];
  const storageLinks = payload.storage_links ?? [];

  const heroImage = attachments.find((att) => att.content_type.startsWith("image/"));
  const markupDoc = attachments.find(
    (att) => att.content_type === "application/pdf" || att.filename.toLowerCase().endsWith(".pdf"),
  );

  return {
    taskId: payload.task_id,
    summary: payload.request_summary ?? "",
    heroImage,
    markupDoc,
    unsupportedStorageLinks: storageLinks.filter((link) => !isSupportedStorageUrl(link.url)),
  };
}
