import { redirect } from "next/navigation";

// Preserve old bookmarks while keeping a single workspace directory.
export default function WorkspaceDirectoryAlias() {
  redirect("/");
}
