import type { OpenLoop } from "./schemas/open-loop.js";

export class FollowThroughAgent {
  scan(loops: OpenLoop[]): OpenLoop[] {
    return loops;
  }
}
