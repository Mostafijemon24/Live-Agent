import { Suspense } from "react";
import { Skeleton } from "@/components/ui";
import { NewTaskPage } from "@/features/new-task/NewTaskPage";

export default function Page() {
  return (
    <Suspense fallback={<Skeleton />}>
      <NewTaskPage />
    </Suspense>
  );
}
