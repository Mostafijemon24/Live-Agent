import { Suspense } from "react";
import { Skeleton } from "@/components/ui";
import { TasksList } from "@/features/tasks/TasksList";

export default function TasksPage() {
  return (
    <Suspense fallback={<Skeleton />}>
      <TasksList />
    </Suspense>
  );
}
