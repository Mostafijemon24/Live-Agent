import { Suspense } from "react";
import { Skeleton } from "@/components/ui";
import { TaskDetail } from "@/features/tasks/TaskDetail";

export default async function TaskPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <Suspense fallback={<Skeleton />}>
      <TaskDetail id={id} />
    </Suspense>
  );
}
