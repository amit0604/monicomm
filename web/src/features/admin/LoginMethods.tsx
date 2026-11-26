import { AuthMethodPanel, type FieldSpec } from "./AuthMethodPanel";
import "./admin.css";

// Module-level, so the panels' callbacks stay stable.
const LDAP_FIELDS: FieldSpec[] = [
  {
    name: "url",
    label: "admin.ldap.url",
    required: true,
    placeholder: "ldaps://dc01.corp.example:636",
  },
  { name: "start_tls", label: "admin.ldap.start_tls", kind: "checkbox" },
  {
    name: "base_dn",
    label: "admin.ldap.base_dn",
    required: true,
    placeholder: "dc=corp,dc=example",
  },
  {
    name: "bind_dn",
    label: "admin.ldap.bind_dn",
    placeholder: "cn=svc-monicomm,ou=service,dc=corp,dc=example",
  },
  { name: "user_filter", label: "admin.ldap.user_filter", required: true },
  {
    name: "admin_group",
    label: "admin.auth.admin_group",
    placeholder: "cn=monicomm-admins,ou=groups,dc=corp,dc=example",
  },
  { name: "technician_group", label: "admin.auth.technician_group" },
  { name: "default_role", label: "admin.auth.default_role", kind: "role" },
  { name: "ca_file", label: "admin.auth.ca_file", placeholder: "/certs/corp-ca.pem" },
];

const SSO_FIELDS: FieldSpec[] = [
  {
    name: "issuer",
    label: "admin.sso.issuer",
    required: true,
    placeholder: "https://idp.corp.internal/realms/it",
  },
  { name: "client_id", label: "admin.sso.client_id", required: true },
  { name: "label", label: "admin.sso.label", required: true },
  { name: "scopes", label: "admin.sso.scopes" },
  { name: "groups_claim", label: "admin.sso.groups_claim" },
  { name: "admin_group", label: "admin.auth.admin_group" },
  { name: "technician_group", label: "admin.auth.technician_group" },
  { name: "default_role", label: "admin.auth.default_role", kind: "role" },
  { name: "redirect_url", label: "admin.sso.redirect_url" },
  { name: "ca_file", label: "admin.auth.ca_file" },
];

/** LDAP / Active Directory and SSO settings on the Admin page. */
export function LoginMethods() {
  return (
    <div className="admin">
      <AuthMethodPanel
        section="ldap"
        title="admin.ldap.title"
        intro="admin.ldap.intro"
        fields={LDAP_FIELDS}
        secret={{ name: "bind_password", label: "admin.ldap.bind_password" }}
        testUser="admin.ldap.test_user"
      />
      <AuthMethodPanel
        section="sso"
        title="admin.sso.title"
        intro="admin.sso.intro"
        fields={SSO_FIELDS}
        secret={{ name: "client_secret", label: "admin.sso.client_secret" }}
      />
    </div>
  );
}
