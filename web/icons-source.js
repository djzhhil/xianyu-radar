// Build with esbuild; only the icons used by this workbench are bundled.
import { createIcons, Users, ListChecks, ScanLine, Search, Settings, RefreshCw, Save, Plus, ChevronLeft, ChevronRight } from "lucide";

for (const prefix of ["sellerItems", "events", "candidates"]) {
  for (const [direction, label, icon] of [["Prev", "上一页", "chevron-left"], ["Next", "下一页", "chevron-right"]]) {
    const button = document.getElementById(`${prefix}${direction}`);
    button.setAttribute("aria-label", label);
    button.title = label;
    const node = document.createElement("i");
    node.setAttribute("data-lucide", icon);
    button.replaceChildren(node);
    button.classList.add("icon-button");
  }
}
createIcons({ icons: { Users, ListChecks, ScanLine, Search, Settings, RefreshCw, Save, Plus, ChevronLeft, ChevronRight } });
