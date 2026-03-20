export type ApprovalStatus = "pending" | "approved" | "denied";

export type ApprovalQueueItem = {
  id: string;
  type: string;
  payload?: Record<string, unknown>;
  status: ApprovalStatus;
  createdAt: string;
};

export class ApprovalEngine {
  #queue: ApprovalQueueItem[] = [];

  enqueue(item: Omit<ApprovalQueueItem, "status" | "createdAt">, now = new Date()) {
    const queued: ApprovalQueueItem = {
      ...item,
      status: "pending",
      createdAt: now.toISOString(),
    };
    this.#queue.push(queued);
    return queued;
  }

  approve(itemId: string) {
    return this.#setStatus(itemId, "approved");
  }

  deny(itemId: string) {
    return this.#setStatus(itemId, "denied");
  }

  list() {
    return [...this.#queue];
  }

  #setStatus(itemId: string, status: ApprovalStatus) {
    const index = this.#queue.findIndex((item) => item.id === itemId);
    if (index === -1) {
      return undefined;
    }
    const updated: ApprovalQueueItem = {
      ...this.#queue[index],
      status,
    };
    this.#queue[index] = updated;
    return updated;
  }
}
