import { Button } from "../../components/ui";
import { RotateCw } from "lucide-react";
import { useText } from "./text";
import type { Loaded } from "./api";

export function Refresh({ loaded }: { loaded: Loaded<unknown> }) {
  const { t, absolute } = useText();
  return (
    <span className="refresh push">
      {loaded.updatedAt && (
        <span>
          {t("updated")} <bdi>{absolute(loaded.updatedAt)}</bdi>
        </span>
      )}
      <Button onClick={loaded.reload} aria-label={t("refresh")} title={t("refresh")}>
        <RotateCw size={16} aria-hidden="true" />
      </Button>
    </span>
  );
}
