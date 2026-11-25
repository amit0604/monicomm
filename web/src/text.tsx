import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

const he = {
  language: "English",
  sections: "חלקי לוח הבקרה",
  overview: "סקירה",
  devices: "מכשירים",
  events: "אירועים",
  demo: "נתוני הדגמה – לא נתוני רשת אמיתיים",
  updated: "עודכן",
  refresh: "רענון",
  retry: "ניסיון חוזר",
  failed: "טעינת הנתונים נכשלה",
  no_source: "אין מקור נתונים מחובר, או שהשרת אינו זמין",
  stale: "הרענון נכשל. מוצגים הנתונים האחרונים שהתקבלו.",
  loading: "טוען נתונים",
  total_devices: "סך המכשירים",
  online_devices: "מכשירים מקוונים",
  disconnected: "מנותקים / חשד לניתוק",
  open_alerts: "התראות פתוחות",
  with_issues: "עם אזהרה או מצב קריטי",
  offline_note: "מנותק",
  suspected_note: "בחשד לניתוק",
  critical_note: "קריטיות",
  of: "מתוך",
  status_overview: "מצב מכשירים",
  recent_events: "אירועים אחרונים",
  view_all: "לכל האירועים",
  no_alerts: "אין התראות פתוחות",
  search_devices: "חיפוש לפי שם, IP, יצרן או דגם",
  search_events: "חיפוש בהודעה, מכשיר או IP",
  all_statuses: "כל המצבים",
  all_types: "כל הסוגים",
  all_vendors: "כל היצרנים",
  all_severities: "כל רמות החומרה",
  all_kinds: "כל המקורות",
  clear: "ניקוי סינון",
  showing: "מוצגים",
  no_results: "לא נמצאו תוצאות",
  no_events: "אין אירועים",
  name: "שם",
  ip: "כתובת IP",
  vendor: "יצרן",
  model: "דגם",
  type: "סוג",
  status: "מצב",
  severity: "חומרה",
  origin: "מקור",
  device: "מכשיר",
  time: "זמן",
  message: "הודעה",
  back: "חזרה למכשירים",
  not_found: "המכשיר לא נמצא",
  information: "פרטי מכשיר",
  metrics: "מדדים אחרונים",
  interfaces: "ממשקים",
  device_events: "אירועי המכשיר",
  no_interfaces: "לא דווחו ממשקים למכשיר זה",
  os: "גרסת מערכת",
  serial: "מספר סידורי",
  site: "אתר",
  unassigned: "ללא שיוך",
  last_poll: "דגימה אחרונה",
  unknown: "לא ידוע",
  cpu: "מעבד",
  memory: "זיכרון",
  temperature: "טמפרטורה",
  uptime: "זמן פעולה",
  days: "ימים",
  no_data: "אין נתון",
  interface: "ממשק",
  speed: "מהירות",
  util_in: "ניצולת נכנסת",
  util_out: "ניצולת יוצאת",
  errors: "שגיאות נכנס/יוצא",
  if_up: "פעיל",
  if_down: "נפל",
  if_disabled: "מושבת",
  s_online: "מקוון",
  s_warning: "אזהרה",
  s_critical: "קריטי",
  s_suspected_offline: "חשד לניתוק",
  s_offline: "מנותק",
  g_critical: "קריטי",
  g_warning: "אזהרה",
  g_info: "מידע",
  g_neutral: "ללא סיווג",
  t_router: "נתב",
  t_switch: "מתג",
  t_firewall: "חומת אש",
  t_server: "שרת",
  t_access_point: "נקודת גישה",
  t_unknown: "לא ידוע",
  a_device_unreachable: "המכשיר אינו מגיב",
  a_interface_down: "ממשק נפל",
  a_high_temperature: "טמפרטורה חריגה",
  a_high_utilization: "ניצולת ממשק גבוהה",
  c_readonly: "קריאה בלבד: מנתח נתונים ואינו מבצע פעולות",
  c_new: "שיחה חדשה",
  c_empty: "שאלו על המכשירים, ההתראות והאירועים",
  c_suggest_1: "מה מצב הרשת כרגע?",
  c_suggest_2: "אילו התראות פתוחות דורשות טיפול ראשון?",
  c_suggest_3: "אילו מכשירים לא מגיבים?",
  c_sources: "מקורות",
  c_devices: "מכשירים",
  c_alerts: "התראות",
  c_events: "אירועים",
  c_collected: "נאספו",
  c_thinking: "אוסף נתונים ומנתח…",
  c_placeholder: "כתבו שאלה…",
  c_send: "שליחה",
  c_notice: "ייתכנו טעויות בתשובות. אין להזין מידע רגיש: בסביבת פיתוח ייתכן שימוש במודל חיצוני.",
  e_no_data_source: "אין מקור נתונים מחובר.",
  e_not_allowed: "אין להשתמש במודל המוגדר בסביבה זו.",
  e_llm_unavailable: "מודל ה-AI אינו זמין כרגע.",
  e_failed: "הבקשה נכשלה.",
};
export type TextKey = keyof typeof he;

const en: Record<TextKey, string> = {
  language: "עברית",
  sections: "Dashboard sections",
  overview: "Overview",
  devices: "Devices",
  events: "Events",
  demo: "Demo data – not real network telemetry",
  updated: "Updated",
  refresh: "Refresh",
  retry: "Try again",
  failed: "Could not load data",
  no_source: "No data source is connected, or the server is unavailable",
  stale: "Refresh failed. Showing the last data received.",
  loading: "Loading data",
  total_devices: "Total devices",
  online_devices: "Online devices",
  disconnected: "Offline / suspected",
  open_alerts: "Open alerts",
  with_issues: "with a warning or critical state",
  offline_note: "offline",
  suspected_note: "suspected",
  critical_note: "critical",
  of: "of",
  status_overview: "Device status",
  recent_events: "Recent events",
  view_all: "All events",
  no_alerts: "No open alerts",
  search_devices: "Search name, IP, vendor or model",
  search_events: "Search message, device or IP",
  all_statuses: "All statuses",
  all_types: "All types",
  all_vendors: "All vendors",
  all_severities: "All severities",
  all_kinds: "All sources",
  clear: "Clear filters",
  showing: "Showing",
  no_results: "No results",
  no_events: "No events",
  name: "Name",
  ip: "IP address",
  vendor: "Vendor",
  model: "Model",
  type: "Type",
  status: "Status",
  severity: "Severity",
  origin: "Source",
  device: "Device",
  time: "Time",
  message: "Message",
  back: "Back to devices",
  not_found: "Device not found",
  information: "Device information",
  metrics: "Latest metrics",
  interfaces: "Interfaces",
  device_events: "Device events",
  no_interfaces: "No interfaces reported for this device",
  os: "OS version",
  serial: "Serial number",
  site: "Site",
  unassigned: "Unassigned",
  last_poll: "Last poll",
  unknown: "Unknown",
  cpu: "CPU",
  memory: "Memory",
  temperature: "Temperature",
  uptime: "Uptime",
  days: "days",
  no_data: "No data",
  interface: "Interface",
  speed: "Speed",
  util_in: "In utilization",
  util_out: "Out utilization",
  errors: "Errors in/out",
  if_up: "Up",
  if_down: "Down",
  if_disabled: "Disabled",
  s_online: "Online",
  s_warning: "Warning",
  s_critical: "Critical",
  s_suspected_offline: "Suspected offline",
  s_offline: "Offline",
  g_critical: "Critical",
  g_warning: "Warning",
  g_info: "Info",
  g_neutral: "Unclassified",
  t_router: "Router",
  t_switch: "Switch",
  t_firewall: "Firewall",
  t_server: "Server",
  t_access_point: "Access point",
  t_unknown: "Unknown",
  a_device_unreachable: "Device not responding",
  a_interface_down: "Interface down",
  a_high_temperature: "Abnormal temperature",
  a_high_utilization: "High interface utilization",
  c_readonly: "Read-only: analyzes data, performs no actions",
  c_new: "New chat",
  c_empty: "Ask about devices, alerts and events",
  c_suggest_1: "What is the network status right now?",
  c_suggest_2: "Which open alerts need attention first?",
  c_suggest_3: "Which devices are not responding?",
  c_sources: "Sources",
  c_devices: "devices",
  c_alerts: "alerts",
  c_events: "events",
  c_collected: "collected",
  c_thinking: "Collecting data and analyzing…",
  c_placeholder: "Ask a question…",
  c_send: "Send",
  c_notice:
    "Answers may be wrong. Do not enter sensitive information: development may use an external model.",
  e_no_data_source: "No data source is connected.",
  e_not_allowed: "The configured model may not be used in this environment.",
  e_llm_unavailable: "The AI model is not available right now.",
  e_failed: "The request failed.",
};

export type Lang = "he" | "en";

interface Text {
  lang: Lang;
  t: (key: TextKey) => string;
  toggle: () => void;
  relative: (iso: string) => string;
  absolute: (iso: string) => string;
}
const Context = createContext<Text | null>(null);

export function useText(): Text {
  const text = useContext(Context);
  if (!text) throw new Error("useText outside TextProvider");
  return text;
}

function storedLang(): Lang {
  try {
    return localStorage.getItem("lang") === "en" ? "en" : "he";
  } catch {
    return "he";
  }
}

export function TextProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<Lang>(storedLang);
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "he" ? "rtl" : "ltr";
    try {
      localStorage.setItem("lang", lang);
    } catch {
      // The choice is simply not remembered.
    }
  }, [lang]);

  const locale = lang === "he" ? "he-IL" : "en-GB";
  const value: Text = {
    lang,
    t: (key) => (lang === "he" ? he : en)[key],
    toggle: () => setLang(lang === "he" ? "en" : "he"),
    relative: (iso) => {
      const minutes = Math.min(0, Math.round((Date.parse(iso) - Date.now()) / 60_000));
      const format = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
      const out =
        minutes > -60
          ? format.format(minutes, "minute")
          : minutes > -1440
            ? format.format(Math.round(minutes / 60), "hour")
            : format.format(Math.round(minutes / 1440), "day");
      return out.replace(" (1)", ""); // Hebrew adds it to the singular
    },
    absolute: (iso) =>
      new Date(iso).toLocaleString(locale, { dateStyle: "short", timeStyle: "medium" }),
  };
  return <Context value={value}>{children}</Context>;
}
