import { FileText } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export function SourceCountBadge({ count, max }: { count: number; max: number }) {
  return (
    <Badge variant="outline" className="gap-1.5 font-normal text-muted-foreground">
      <FileText className="size-3" />
      {count} of {max} sources
    </Badge>
  );
}
