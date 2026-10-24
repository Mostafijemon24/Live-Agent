import { Suspense } from "react";
import { ApprovalsScreen } from "@/features/approvals/ApprovalsScreen";

export default function Page() {
  return (
    <Suspense>
      <ApprovalsScreen />
    </Suspense>
  );
}
