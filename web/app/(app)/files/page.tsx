import { Suspense } from "react";
import { FilesScreen } from "@/features/files/FilesScreen";

export default function Page() {
  return (
    <Suspense>
      <FilesScreen />
    </Suspense>
  );
}
