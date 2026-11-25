// Fixed replies for guardrail intents, in English and Hebrew.
// These are deliberate, honest statements about the prototype, not generated text.
import type { Lang } from './knowledge';
import { KNOWLEDGE } from './knowledge';

type Text = Record<Lang, string>;

const KB_TOPICS = KNOWLEDGE.filter((e) => e.covers.length === 1).map((e) => e.title.en).join(', ');

export const REPLIES = {
  greeting: {
    en: "Hi! I'm ChatIAF, MoniComm's network assistant. Ask me about devices, ports, alerts, config changes, or a networking concept.",
    he: 'שלום! אני ChatIAF, עוזר הרשת של MoniComm. אפשר לשאול אותי על רכיבים, פורטים, התראות, שינויי הגדרות או מושגי רשת.',
  },
  thanks: {
    en: "You're welcome. Anything else on the network?",
    he: 'בשמחה. עוד משהו ברשת?',
  },
  capabilities: {
    en:
      'I can:\n' +
      '- **Read** device, port, syslog, alert and config-history data, and explain what I find with sources.\n' +
      '- **Explain** common networking concepts (TCP/UDP, DNS, DHCP, switching, routing, OSI and more) from a local knowledge base.\n' +
      '- **Draft** a change with an impact analysis. Only a technician can approve it.\n\n' +
      "I can't apply changes, and I only cover networking, communications and IT infrastructure.\n\n" +
      '**Prototype mode:** no AI model is connected yet. Replies come from local rules, scripted demo scenarios on mock data, and the local knowledge base.',
    he:
      'אני יכול:\n' +
      '- **לקרוא** נתוני רכיבים, פורטים, syslog, התראות והיסטוריית שינויים, ולהסביר מה מצאתי עם מקורות.\n' +
      '- **להסביר** מושגי רשת נפוצים (TCP/UDP, DNS, DHCP, מיתוג, ניתוב, מודל OSI ועוד) ממאגר ידע מקומי.\n' +
      '- **לנסח** שינוי עם ניתוח השפעה. רק טכנאי יכול לאשר אותו.\n\n' +
      'אני לא יכול לבצע שינויים, ואני עוסק רק ברשתות, תקשורת ותשתיות IT.\n\n' +
      '**מצב אב-טיפוס:** עדיין לא מחובר מודל AI. התשובות מגיעות מחוקים מקומיים, מתרחישי דמה על נתונים מדומים וממאגר הידע המקומי.',
  },
  provenance: {
    en:
      "**Mock data, simulated AI.** This is a prototype:\n" +
      '- All network data (devices, ports, logs, alerts, config changes) is **synthetic mock data** for one fictional site.\n' +
      '- **No AI model is connected.** Replies come from a rule-based intent classifier, scripted demo scenarios and a small local knowledge base.\n' +
      '- **No real network or device is connected.** The "configurator" that runs approved changes is a local simulation; nothing leaves this browser.',
    he:
      '**נתונים מדומים ו-AI מדומה.** זהו אב-טיפוס:\n' +
      '- כל נתוני הרשת (רכיבים, פורטים, לוגים, התראות, שינויי הגדרות) הם **נתונים סינתטיים** של אתר בדיוני אחד.\n' +
      '- **לא מחובר מודל AI.** התשובות מגיעות ממסווג כוונות מבוסס חוקים, מתרחישי דמה כתובים מראש וממאגר ידע מקומי קטן.\n' +
      '- **לא מחוברים רשת או ציוד אמיתיים.** ה-"configurator" שמבצע שינויים מאושרים הוא סימולציה מקומית, ושום דבר לא יוצא מהדפדפן.',
  },
  permission: {
    en:
      "**No. I can't make changes by myself.** ChatIAF is read-only by design:\n" +
      '- I can read data, explain it, and **draft** a change with an impact analysis.\n' +
      '- Nothing runs until a technician presses **Approve**. Routers, firewalls and core switches need a **second approver**.\n' +
      '- After approval, the change goes to the configurator, not to me. I have no tool that can reach it.\n\n' +
      'In this prototype even approved changes are **simulated locally**. No device is contacted.',
    he:
      '**לא. אני לא יכול לבצע שינויים בעצמי.** ChatIAF בנוי לקריאה בלבד:\n' +
      '- אני יכול לקרוא נתונים, להסביר אותם ו**לנסח** שינוי עם ניתוח השפעה.\n' +
      '- שום דבר לא מתבצע עד שטכנאי לוחץ **אשר**. נתבים, חומות אש ומתגי ליבה דורשים **מאשר שני**.\n' +
      '- אחרי האישור, השינוי עובר ל-configurator ולא אליי. אין לי שום כלי שמגיע אליו.\n\n' +
      'באב-טיפוס הזה גם שינויים מאושרים **מדומים באופן מקומי**, ואף רכיב לא מקבל פקודה.',
  },
  outOfScope: {
    en: "Sorry, that's outside what I cover. I'm specialized in networking, computer communications and IT infrastructure: devices, protocols, monitoring, logs and alerts, troubleshooting and defensive security. Happy to help with any of those.",
    he: 'מצטער, זה מחוץ לתחום שלי. אני מתמחה ברשתות, תקשורת מחשבים ותשתיות IT: רכיבים, פרוטוקולים, ניטור, לוגים והתראות, איתור תקלות ואבטחת מידע הגנתית. אשמח לעזור בכל אחד מאלה.',
  },
  mixedPrefix: {
    en: "Part of your question is outside my scope, so I'll skip it and answer only the networking part.",
    he: 'חלק מהשאלה מחוץ לתחום שלי, אז אדלג עליו ואענה רק על החלק המקצועי.',
  },
  policy: {
    en: "I can't change my role or my rules. I'm ChatIAF, a read-only assistant for networking and IT infrastructure, and every change needs a technician's approval. Happy to help with a network question.",
    he: 'אני לא יכול לשנות את התפקיד או את הכללים שלי. אני ChatIAF, עוזר לקריאה בלבד לרשתות ותשתיות IT, וכל שינוי דורש אישור של טכנאי. אשמח לעזור בשאלה על הרשת.',
  },
  ambiguous: {
    en: "I'm not sure what you're asking. Could you be more specific? For example, name a device (core-sw-01), a port (Gi1/0/5 on access-sw-12), an IP (10.1.4.22) or a concept (DNS, VLAN, OSPF).\n\nIn this prototype I match questions with simple local rules, so specific wording helps.",
    he: 'לא בטוח שהבנתי את השאלה. אפשר לפרט? למשל שם של רכיב (core-sw-01), פורט (Gi1/0/5 ב-access-sw-12), כתובת IP (10.1.4.22) או מושג (DNS, VLAN, OSPF).\n\nבאב-טיפוס הזה אני מזהה שאלות לפי חוקים מקומיים פשוטים, אז ניסוח מדויק עוזר.',
  },
  noContext: {
    en: "What would you like me to explain? There's no earlier topic in this chat yet. Tell me the device, port or concept.",
    he: 'מה תרצה שאסביר? עדיין אין נושא קודם בשיחה הזו. ציין רכיב, פורט או מושג.',
  },
  noContextTopic: {
    en: "I'm not sure which part of my last answer you mean. Could you name the device, port or concept you want explained?",
    he: 'לא בטוח לאיזה חלק בתשובה הקודמת התכוונת. אפשר לציין את הרכיב, הפורט או המושג שתרצה שאסביר?',
  },
  notInKb: {
    en: `I don't have a reliable answer for that in the local knowledge base yet, and no AI model is connected to answer general questions in this prototype.\n\nTopics I can explain now: ${KB_TOPICS}.`,
    he: `עדיין אין לי תשובה אמינה לזה במאגר הידע המקומי, ובאב-טיפוס הזה לא מחובר מודל AI שעונה על שאלות כלליות.\n\nנושאים שאני יכול להסביר כרגע: ${KB_TOPICS}.`,
  },
  scenarioEnglishOnly: {
    en: '',
    he: 'תוצאות נתוני הרשת בדמו זמינות כרגע באנגלית בלבד:',
  },
  backgroundFor: {
    en: 'Background for the previous finding:',
    he: 'רקע לממצא הקודם:',
  },
  kbExhausted: {
    en: "That's everything the local knowledge base has on **{title}**. Going deeper needs a connected AI model, which this prototype doesn't have yet.",
    he: 'זה כל מה שיש במאגר הידע המקומי על **{title}**. כדי להעמיק נדרש מודל AI מחובר, ועדיין אין כזה באב-טיפוס.',
  },
  kbLabel: {
    en: 'local knowledge base',
    he: 'מאגר ידע מקומי',
  },
} satisfies Record<string, Text>;

export function reply(key: keyof typeof REPLIES, lang: Lang, vars: Record<string, string> = {}) {
  let text: string = REPLIES[key][lang];
  for (const [k, v] of Object.entries(vars)) text = text.replaceAll(`{${k}}`, v);
  return text;
}

export function isThanks(text: string) {
  return /\b(thanks|thank you|thx|cheers)\b|תודה/i.test(text);
}
