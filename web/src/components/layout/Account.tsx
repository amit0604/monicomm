import { LogOut } from "lucide-react";
import { useSession, useSignOut } from "../../features/auth/session";
import { useI18n } from "../../i18n";
import { Button } from "../ui";

function initials(name: string): string {
  const parts = name.split(/[\s._@-]+/).filter(Boolean);
  const letters = parts.length > 1 ? parts[0][0] + parts[1][0] : name.slice(0, 2);
  return letters.toUpperCase();
}

/** The signed-in account at the bottom of the side navigation. Nothing when login is off. */
export function Account({ collapsed }: { collapsed: boolean }) {
  const { t } = useI18n();
  const user = useSession();
  const signOut = useSignOut();
  if (!user || !signOut) return null;

  const shown = user.display_name || user.name;
  const role = t(`admin.users.role_${user.role}`);
  const source = t(`account.source.${user.source ?? "local"}`);

  return (
    <section
      className={collapsed ? "account account--collapsed" : "account"}
      aria-label={t("account.title")}
    >
      <span className="account__avatar" aria-hidden="true" title={collapsed ? shown : undefined}>
        {initials(shown)}
      </span>
      {collapsed ? (
        <span className="visually-hidden">{`${shown}, ${role}`}</span>
      ) : (
        <div className="account__info">
          <bdi className="account__name">{shown}</bdi>
          {user.display_name && user.display_name !== user.name && (
            <bdi className="account__line">{user.name}</bdi>
          )}
          {user.email && <bdi className="account__line">{user.email}</bdi>}
          <span className="account__line">{`${role} · ${source}`}</span>
        </div>
      )}
      <Button
        variant="ghost"
        size="sm"
        iconOnly
        aria-label={t("auth.sign_out")}
        title={t("auth.sign_out")}
        onClick={signOut}
      >
        <LogOut size={16} aria-hidden="true" className="flip-rtl" />
      </Button>
    </section>
  );
}
