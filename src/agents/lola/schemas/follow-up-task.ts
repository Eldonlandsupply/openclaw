export interface FollowUpTask {
  id: string;
  openLoopId: string;
  title: string;
  taskType?: string;
  owner?: string;
  dueAt?: string;
  priority?: "low" | "medium" | "high" | "urgent";
  status?: string;
  notes?: string;
}
