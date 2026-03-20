export type LolaTaskPayload = Record<string, unknown>;

export type LolaTask = {
  id: string;
  type: string;
  payload?: LolaTaskPayload;
};

export class LolaOrchestrator {
  #running = false;
  #queue: LolaTask[] = [];
  #seenTaskIds = new Set<string>();

  start() {
    this.#running = true;
  }

  stop() {
    this.#running = false;
  }

  isRunning() {
    return this.#running;
  }

  enqueue(task: LolaTask) {
    if (!this.#seenTaskIds.has(task.id)) {
      this.#queue.push(task);
      this.#seenTaskIds.add(task.id);
    }
  }

  next() {
    return this.#queue.shift();
  }

  route(task: LolaTask) {
    this.enqueue(task);
    return `queued:${task.type}`;
  }
}
