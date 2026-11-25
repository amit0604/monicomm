// Local, rule-based intent classifier for the ChatIAF prototype.
//
// LIMITS (be honest about what this is):
// - It is pattern matching over English and Hebrew phrases, not semantic understanding.
//   A real model replaces it later; until then, unknown phrasings fall to AMBIGUOUS (ask to clarify)
//   instead of being forced into a demo scenario.
// - A demo scenario only runs when the question names the thing it is about (a device, port or IP)
//   or uses an anchored phrase ("what changed", "active alerts"). A single loose keyword never triggers one.
// - Follow-ups resolve against the previous reply's topic only (no deeper coreference).
import { CONCEPTS } from './knowledge';
import type { Lang } from './knowledge';
import { DEVICES } from './network';

export type Intent =
  | 'TECHNICAL_KNOWLEDGE'
  | 'NETWORK_INFORMATION'
  | 'CONFIG_HISTORY'
  | 'ALERT_INFORMATION'
  | 'INCIDENT_INFORMATION'
  | 'IMPACT_INFORMATION'
  | 'SYSTEM_CAPABILITIES'
  | 'DATA_PROVENANCE'
  | 'PERMISSION_QUESTION'
  | 'FOLLOW_UP'
  | 'GREETING'
  | 'OUT_OF_SCOPE'
  | 'AMBIGUOUS'
  | 'MIXED'
  | 'POLICY_VIOLATION';

/** Existing demo flows a classification may run. */
export type Scenario = 'port_down' | 'shutdown' | 'wan' | 'config_changes' | 'alerts' | 'host' | 'device_status';

export interface Entities {
  device?: string;
  iface?: string;
  ip?: string;
  concepts: string[];
}

export interface Classification {
  intent: Intent;
  confidence: 'high' | 'medium' | 'low';
  lang: Lang;
  entities: Entities;
  scenario?: Scenario;
  /** For MIXED: the in-scope part to answer. */
  inScope?: Classification;
  /** Why this intent was chosen; shown in tests and debugging. */
  reason: string;
}

/** What the previous assistant reply was about, so follow-ups can refer back to it. */
export interface TurnContext {
  intent: Intent;
  concepts: string[];
  entries: string[];
  scenario?: Scenario;
  detailShown?: boolean;
}

export interface ConversationContext {
  turns: TurnContext[];
}

const SCENARIO_INTENT: Record<Scenario, Intent> = {
  port_down: 'INCIDENT_INFORMATION',
  wan: 'INCIDENT_INFORMATION',
  shutdown: 'IMPACT_INFORMATION',
  config_changes: 'CONFIG_HISTORY',
  alerts: 'ALERT_INFORMATION',
  host: 'NETWORK_INFORMATION',
  device_status: 'NETWORK_INFORMATION',
};

// ---------- matchers ----------

const HEB = /[֐-׿]/;
const HE_PREFIX = '[ובלהמשכ]{0,2}';

function escape(s: string) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Whole-word, case-insensitive English match. Never a prefix match ("diff" must not match "difference"). */
function enWord(term: string) {
  return new RegExp(`(?<![\\w-])${escape(term).replace(/\s+/g, '\\s+')}(?![\\w-])`, 'i');
}

/** Hebrew stem with optional attached prefixes (ל-נתב, והמתג). \b doesn't work for Hebrew letters in JS. */
function heWord(stem: string) {
  return new RegExp(`(?:^|[^\\u0590-\\u05FF])${HE_PREFIX}${escape(stem)}(?![\\u0590-\\u05FF])`);
}

const any = (text: string, patterns: RegExp[]) => patterns.some((p) => p.test(text));

const DEVICE_RE = new RegExp(`(?<![\\w-])(${DEVICES.map((d) => escape(d.name)).join('|')})(?![\\w-])`, 'i');
const IF_RE = /(?<![\w-])((?:gi(?:gabitethernet)?|te(?:ngigabitethernet)?|xe|ge|et|po(?:rt-channel)?)-?\d+(?:\/\d+){1,3})(?![\w/])/i;
const IP_RE = /(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])/;

const POLICY_VIOLATION = [
  /ignore (all |any |the )?(previous|prior|above|earlier|your) (instructions|rules|prompts?|guidelines)/i,
  /disregard (all |any |the |your )?(previous |prior )?(instructions|rules|guidelines|policy)/i,
  /forget (all |your |the )?(previous |prior )?(instructions|rules|guidelines)/i,
  /\byou are now\b/i,
  /\bfrom now on,? you (are|will)\b/i,
  /\b(act|behave) as (an? )?(general|unrestricted|different|new)\b/i,
  /\bpretend (to be|you are)\b/i,
  /\b(jailbreak|developer mode|dan mode)\b/i,
  /\b(show|reveal|print|repeat|tell me) (me )?(your|the) (system )?(prompt|instructions)\b/i,
  /\b(without|skip|bypass|no) (the )?(approval|confirmation|human)\b.*\b(apply|change|run|execute|push)\b/i,
  /\b(apply|change|run|execute|push)\b.*\b(without|skipping|bypassing) (the )?(approval|confirmation)\b/i,
  /\b(hack into|break into|exploit (a|the|their)|ddos|crack (the |a )?password|steal (credentials|passwords))\b/i,
  /התעלם מ(כל )?ה?(הוראות|הנחיות|כללים)/,
  /שכח את (כל )?ה?(הוראות|הנחיות|כללים)/,
  /אתה עכשיו/,
  /מעכשיו אתה/,
  /תתנהג כ/,
  /(הצג|תראה|חשוף) (לי )?את ה?(הנחיות|הוראות) (המערכת|שלך)/,
  /בלי אישור/,
];

const GREETING = /^(hi|hello|hey|good (morning|afternoon|evening)|thanks|thank you|thx|cheers|ok(ay)?|great|cool|שלום|היי|הי|תודה( רבה)?|בוקר טוב|ערב טוב|צהריים טובים|מעולה|אחלה)[\s!.,🙂👍]*$/iu;

const CAPABILITIES = [
  /\bwhat (can|could) you (do|help)/i,
  /\bhow (can|could|do) you help\b/i,
  /\bwhat are you( able to do)?\??$/i,
  /\bwho are you\b/i,
  /\byour (capabilities|features|abilities|limitations)\b/i,
  /\bhow (do|can) i use (you|this|chatiaf|monicomm)\b/i,
  /\bwhat do you know\b/i,
  /^help\??$/i,
  /מה אתה (יכול|יודע)/,
  /במה אתה (יכול )?(לעזור|עוזר)/,
  /מי אתה/,
  /מה ה?יכולות/,
  /איך משתמשים/,
];

const PROVENANCE = [
  // "real-time data" is a monitoring question, not a provenance one.
  /\b(real|mock|fake|simulated|synthetic|dummy)\b(?![- ]time)[\w\s-]{0,20}\b(data|network|devices?|model|ai|llm)\b/i,
  /\b(data|network|devices?|model|ai|llm)\b[\w\s-]{0,20}\b(real|mock|fake|simulated|synthetic)\b(?![- ]time)/i,
  /\b(is|are) (this|the|these|it|you|your) (data |network |answers? |devices? )?(real|live|actual|mock|fake|simulated|a demo)\b(?![- ]time)/i,
  /\b(connected|hooked up|linked) to (a |the |any )?(real |live |actual )?(network|model|devices?|ai|llm)\b/i,
  /\b(which|what) (ai |language )?(model|llm)\b/i,
  /\bare you (an? )?(real |actual )?(ai|llm|language model|model)\b/i,
  /\bwhere (does|do) (this|the|your) (data|information|answers?) come from\b/i,
  /נתונים (אמיתיים|מדומים|מזויפים|סינתטיים)/,
  /נתוני (דמה|אמת)/,
  /(רשת|מודל|ציוד|נתונים) (אמיתי|אמיתית|אמיתיים|חי|חיה)/,
  /איזה מודל/,
  /מחובר (ל)?(רשת|מודל|ציוד)/,
  /מאיפה (ה)?(נתונים|מידע|תשובות)/,
];

const PERMISSION_VERB = /\b(change|changes|modify|configure|reconfigure|apply|execute|run (commands?|scripts?)|push|write|shut ?down|reboot|restart|delete|make changes|take action)\b/i;
const PERMISSION_FORM = [
  /\b(can|could|will|would|are) you (be )?(able to |allowed to |permitted to |authorized to )?/i,
  /\b(do|does) (you|chatiaf|the ai) have (the )?(permission|access|rights?|authority)\b/i,
  /\b(allowed|permitted|authorized|able) to\b/i,
];
const SELF_AGENCY = /\b(by yourself|on your own|yourself|autonomously|automatically|without (me|my|a|any|human)|directly)\b/i;
const WRITE_ACCESS = /\b(write|admin|root|enable|config(uration)?|read[- ]write) (access|permissions?|rights?|privileges?)\b/i;
const PERMISSION_HE = [
  /(יכול|מסוגל|מורשה|רשאי|מוסמך)[^?]*(לשנות|לבצע|להריץ|לכבות|לעדכן|לכתוב|להחיל|שינויים)/,
  /הרשא(ה|ות) (כתיבה|ניהול|לשנות|לבצע)/,
  /(בעצמך|לבד|אוטומטית|באופן עצמאי)/,
];

const OUT_OF_SCOPE = [
  ...[
    // Avoid words with an IT meaning too ("series" of switches, file "shares").
    'movie', 'movies', 'film', 'films', 'tv show', 'tv series', 'netflix', 'song', 'songs', 'music', 'singer',
    'sport', 'sports', 'football', 'soccer', 'basketball', 'nba', 'world cup', 'match score',
    'politics', 'political', 'election', 'elections', 'president', 'prime minister', 'government', 'party leader',
    'invest', 'investing', 'investment', 'stocks', 'stock market', 'crypto', 'bitcoin', 'ethereum', 'forex',
    'recipe', 'cooking', 'restaurant', 'dating', 'girlfriend', 'boyfriend', 'relationship', 'marriage', 'love life',
    'horoscope', 'weather', 'joke', 'jokes', 'poem', 'vacation', 'celebrity', 'gossip',
  ].map(enWord),
  ...['סרט', 'סרטים', 'סדרה', 'סדרות', 'שיר', 'שירים', 'מוזיקה', 'זמר', 'ספורט', 'כדורגל', 'כדורסל', 'פוליטיקה',
    'בחירות', 'ממשלה', 'ראש הממשלה', 'השקעה', 'להשקיע', 'מניות', 'מניה', 'ביטקוין', 'קריפטו', 'מתכון', 'בישול',
    'מסעדה', 'זוגיות', 'חברה שלי', 'החבר שלי', 'דייט', 'מזג אוויר', 'בדיחה', 'חופשה'].map(heWord),
];

const KNOWLEDGE_FORM = [
  /^(what|what's|whats|explain|define|describe|tell me about|how does|how do|how is|why does|why do|why is|compare)\b/i,
  /\b(what is|what are|what's|meaning of|difference between|differences between|compared to|versus|vs\.?)\b/i,
  /^(מה זה|מהו|מהי|מה הם|מה הן|הסבר|תסביר|הגדר|איך עובד|איך עובדת|למה משמש|מה התפקיד)/,
  /מה ההבדל|ההבדלים בין|לעומת/,
];

const FOLLOW_UP = [
  /^(why|how|how so|and|so|really)\??!?$/i,
  /^(why|how) (is|does|did) (it|that|this)\b/i,
  /\b(explain|describe|clarify) (it|that|this|them)\b/i,
  /\b(explain|go) (further|more|again|deeper)\b/i,
  /\b(in )?more detail\b/i,
  /\b(tell me more|elaborate|more details?|go on|expand on (it|that))\b/i,
  /\bwhat does (it|that|this) mean\b/i,
  /\b(say|explain) (it|that) again\b/i,
  /\bdifference between them\b/i,
  /\bwhat about (it|that|them)\b/i,
  /^(למה|מדוע|איך)\??$/,
  /ביניהם/,
  /(תוכל|אפשר|תסביר|הסבר)[^?]*(שוב|יותר|בפירוט|לעומק|את זה)/,
  /מה זה אומר/,
  /(פרט|תרחיב|עוד פרטים|תמשיך)/,
];

const COMPARE_FOLLOW_UP = /\b(difference|differ|compare|comparison|versus|vs)\b|ההבדל|ביניהם|לעומת/i;

// Network vocabulary: in-domain, even when the local knowledge base has no entry for it.
const NETWORK_TERMS = [
  ...[
    'ip', 'ipv4', 'ipv6', 'subnet', 'subnetting', 'netmask', 'cidr', 'gateway', 'nat', 'pat', 'bgp', 'eigrp', 'rip', 'is-is',
    'mpls', 'qos', 'vpn', 'ipsec', 'gre', 'tls', 'ssl', 'https', 'http', 'ftp', 'sftp', 'ssh', 'telnet', 'icmp', 'ping',
    'traceroute', 'latency', 'jitter', 'packet loss', 'bandwidth', 'throughput', 'mtu', 'ethernet', 'wifi', 'wi-fi',
    'wireless', 'lan', 'wan', 'trunk', 'lacp', 'port channel', 'etherchannel', 'port', 'ports', 'interface', 'interfaces',
    'firewall', 'proxy', 'load balancer', 'server', 'servers', 'network', 'networks', 'networking', 'protocol', 'protocols',
    'packet', 'packets', 'frame', 'frames', 'mac', 'mac address', 'hub', 'modem', 'fiber', 'optic', 'sfp', 'poe', 'nic',
    'active directory', 'ldap', 'kerberos', 'radius', 'tacacs', 'siem', 'ids', 'ips', 'malware', 'phishing', 'ransomware',
    'vulnerability', 'patch', 'hardening', 'backup', 'raid', 'virtualization', 'vmware', 'vcenter', 'docker', 'kubernetes',
    'linux', 'windows server', 'monitoring', 'alert', 'alerts', 'log', 'logs', 'incident', 'root cause', 'outage',
    'netflow', 'sflow', 'pcap', 'wireshark', 'ntp', 'layer 2', 'layer 3', 'l2', 'l3', 'broadcast', 'multicast', 'unicast',
    'topology', 'uplink', 'downlink', 'redundancy', 'failover', 'monicomm', 'chatiaf', 'configurator', 'impact',
  ].map(enWord),
  ...['רשת', 'רשתות', 'תקשורת', 'שרת', 'שרתים', 'חומת אש', 'פורט', 'פורטים', 'ממשק', 'כתובת', 'פרוטוקול',
    'שכבה', 'ניטור', 'לוג', 'לוגים', 'התראה', 'התראות', 'תקלה', 'תקלות', 'קישור', 'סיב', 'ניתוב', 'אבטחת מידע',
    'סייבר', 'גיבוי', 'וירטואליזציה', 'מונים'].map(heWord),
];

const CONCEPT_MATCHERS = CONCEPTS.map((c) => ({
  id: c.id,
  patterns: [...c.en.map(enWord), ...(c.he ?? []).map(heWord)],
}));

// Anchored scenario phrases.
const DOWN_WORDS = /\b(down|why|err-?disabled?|not working|broken|dead|recover|fix|flapping|flap|issue|problem|offline|failing|failed)\b|נפל|נופל|למה|לא עובד|תקלה|מושבת|מנותק/i;
const SHUT_WORDS = /\b(shut ?down|shut|disable|turn off|bring down|admin down)\b|תכבה|לכבות|כבה|השבת|תשבית/i;
const IMPACT_WORDS = /\b(what (would|will) happen|impact|affect(ed)?|what if|consequences?|risk)\b|מה יקרה|השפעה|ישפיע/i;
const WAN_ANCHOR = /\b(wan|site-north|edge-rtr-01|xe-0\/1\/[01])\b/i;
const WAN_PROBLEM = /\b(slow|slowness|latency|delay|errors?|crc|drops?|congest\w*|saturat\w*|loss|down|flap\w*|fix|reroute|what can we do|help|issue|problem)\b|איטי|תקלה|עומס|מה אפשר/i;
const CONFIG_HISTORY = [
  /\bwhat (has |have )?(changed|was changed|got changed)\b/i,
  /\bwho (changed|modified|touched|edited)\b/i,
  /\b(config(uration)?|running[- ]config) (changes?|history|diffs?|commits?)\b/i,
  /\b(recent|latest|last|any|show|list) (config(uration)? )?(changes|commits|modifications)\b/i,
  /\bchange (log|history)\b/i,
  /\bchanged since\b/i,
  /מה (השתנה|שונה)/,
  /מי שינה/,
  // "שינוי תצורה" alone is a concept; it's history only with a time/recency marker.
  /שינויי?ם? (ב)?(קונפיגורציה|תצורה|הגדרות)[^?]*(אחרונים|לאחרונה|מאתמול|אתמול|היום|השבוע|האחרון)/,
  /היסטוריית שינויים/,
];
const ALERTS = [
  /\b(show|list|any|active|open|current|recent|critical|outstanding|today'?s?)\b[\w\s]{0,20}\balerts?\b/i,
  /\balerts?\b[\w\s]{0,15}\b(now|active|open|today|right now)\b/i,
  /^alerts?\??$/i,
  /התראות (פעילות|פתוחות|קריטיות)?/,
];
const HOST_WORDS = /\b(where|which (switch|port)|find|locate|located|connected|plugged|on which|host|lookup|look up)\b|איפה|מחובר|באיזה (מתג|פורט)/i;
const STATUS_WORDS = /\b(status|state|health|how is|how's|show|details|info|up|down)\b|מצב|סטטוס|תראה/i;

// ---------- classifier ----------

export function detectLang(text: string): Lang {
  return HEB.test(text) ? 'he' : 'en';
}

export function extractEntities(text: string): Entities {
  const concepts = CONCEPT_MATCHERS.filter((c) => any(text, c.patterns)).map((c) => c.id);
  return {
    device: text.match(DEVICE_RE)?.[1]?.toLowerCase(),
    iface: text.match(IF_RE)?.[1],
    ip: text.match(IP_RE)?.[1],
    concepts,
  };
}

function isPermissionQuestion(text: string, e: Entities) {
  const he = any(text, PERMISSION_HE) && (/(בעצמך|לבד|אוטומטית|באופן עצמאי|הרשא)/.test(text) || !e.iface);
  if (he) return true;
  if (WRITE_ACCESS.test(text)) return true;
  const asks = any(text, PERMISSION_FORM) && PERMISSION_VERB.test(text);
  // "Can you shut down Gi1/0/48?" is an action request (goes through IMPACT + approval);
  // "Can you make changes by yourself?" / "Are you allowed to change configs?" is a permission question.
  return asks && (SELF_AGENCY.test(text) || !e.iface);
}

function matchScenario(text: string, e: Entities): Scenario | undefined {
  if (e.iface && (SHUT_WORDS.test(text) || IMPACT_WORDS.test(text))) return 'shutdown';
  if (e.iface && DOWN_WORDS.test(text)) return 'port_down';
  if (WAN_ANCHOR.test(text) && (WAN_PROBLEM.test(text) || e.device === 'edge-rtr-01')) return 'wan';
  if (e.ip && (HOST_WORDS.test(text) || text.trim() === e.ip)) return 'host';
  if (any(text, CONFIG_HISTORY)) return 'config_changes';
  if (any(text, ALERTS)) return 'alerts';
  if ((e.device || e.iface) && STATUS_WORDS.test(text)) return 'device_status';
  if ((e.device || e.iface) && text.replace(DEVICE_RE, '').replace(IF_RE, '').trim().length < 4) return 'device_status';
  return undefined;
}

function classifyInScope(text: string, e: Entities, lang: Lang, ctx: ConversationContext): Classification {
  if (any(text, PROVENANCE)) return { intent: 'DATA_PROVENANCE', confidence: 'high', lang, entities: e, reason: 'asks whether data/model are real' };
  if (isPermissionQuestion(text, e)) return { intent: 'PERMISSION_QUESTION', confidence: 'high', lang, entities: e, reason: 'asks what the AI may change' };
  if (any(text, CAPABILITIES)) return { intent: 'SYSTEM_CAPABILITIES', confidence: 'high', lang, entities: e, reason: 'asks what ChatIAF can do' };

  const scenario = matchScenario(text, e);
  if (scenario) {
    return { intent: SCENARIO_INTENT[scenario], scenario, confidence: 'high', lang, entities: e, reason: `anchored match for demo scenario "${scenario}"` };
  }

  const knowledgeForm = any(text, KNOWLEDGE_FORM);
  if (e.concepts.length > 0 && (knowledgeForm || e.concepts.length >= 2 || text.trim().split(/\s+/).length <= 3)) {
    return { intent: 'TECHNICAL_KNOWLEDGE', confidence: 'high', lang, entities: e, reason: `concepts: ${e.concepts.join(', ')}` };
  }

  if (any(text, FOLLOW_UP)) {
    const last = ctx.turns.at(-1);
    return last
      ? { intent: 'FOLLOW_UP', confidence: 'medium', lang, entities: e, reason: `refers to previous ${last.intent}` }
      : { intent: 'AMBIGUOUS', confidence: 'low', lang, entities: e, reason: 'follow-up with no previous topic' };
  }

  const networkish = e.concepts.length > 0 || any(text, NETWORK_TERMS);
  if (knowledgeForm && networkish) {
    return { intent: 'TECHNICAL_KNOWLEDGE', confidence: 'medium', lang, entities: e, reason: 'networking question, no local knowledge entry' };
  }
  return { intent: 'AMBIGUOUS', confidence: 'low', lang, entities: e, reason: networkish ? 'in-domain words but no clear request' : 'no in-domain signal' };
}

export function classify(question: string, ctx: ConversationContext = { turns: [] }): Classification {
  const text = question.trim();
  const lang = detectLang(text);
  const e = extractEntities(text);

  if (!text) return { intent: 'AMBIGUOUS', confidence: 'low', lang, entities: e, reason: 'empty' };
  if (any(text, POLICY_VIOLATION)) return { intent: 'POLICY_VIOLATION', confidence: 'high', lang, entities: e, reason: 'tries to override instructions or the approval rule' };
  if (GREETING.test(text)) return { intent: 'GREETING', confidence: 'high', lang, entities: e, reason: 'greeting or thanks' };

  const outOfScope = any(text, OUT_OF_SCOPE);
  const inScope = classifyInScope(text, e, lang, ctx);

  if (outOfScope) {
    const hasInScopePart = inScope.intent !== 'AMBIGUOUS' && inScope.intent !== 'FOLLOW_UP';
    return hasInScopePart
      ? { intent: 'MIXED', confidence: 'medium', lang, entities: e, inScope, reason: `out-of-scope topic plus ${inScope.intent}` }
      : { intent: 'OUT_OF_SCOPE', confidence: 'high', lang, entities: e, reason: 'off-topic subject' };
  }
  return inScope;
}

export function wantsComparison(question: string) {
  return COMPARE_FOLLOW_UP.test(question);
}
