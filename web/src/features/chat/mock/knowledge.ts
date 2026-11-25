// Local knowledge base: short, static reference text for common networking concepts.
// It is NOT an AI model. Answers from here are labeled "Local knowledge base" in the UI.
// Topics outside this list get an explicit "not available yet" reply instead of a made-up answer.

export type Lang = "en" | "he";
type Text = Record<Lang, string>;

export interface Concept {
  id: string;
  /** English matchers: whole words, case-insensitive. */
  en: string[];
  /** Hebrew stems: matched with optional one/two-letter prefixes (ו, ה, ב, ל, מ, ש, כ). */
  he?: string[];
}

export interface KnowledgeEntry {
  id: string;
  title: Text;
  /** Concepts this entry explains. Two concepts = a comparison entry. */
  covers: string[];
  summary: Text;
  detail: Text;
}

export const CONCEPTS: Concept[] = [
  { id: "tcp", en: ["tcp"] },
  { id: "udp", en: ["udp"] },
  { id: "dns", en: ["dns", "domain name system", "name resolution"] },
  { id: "dhcp", en: ["dhcp"] },
  { id: "switch", en: ["switch", "switches", "switching"], he: ["מתג", "מתגים"] },
  { id: "router", en: ["router", "routers", "routing"], he: ["נתב", "נתבים", "ניתוב"] },
  { id: "osi", en: ["osi", "osi model", "seven layers", "7 layers"], he: ["מודל השכבות"] },
  { id: "vlan", en: ["vlan", "vlans"] },
  {
    id: "stp",
    en: [
      "stp",
      "spanning tree",
      "spanning-tree",
      "bpdu",
      "bpdu guard",
      "bpduguard",
      "err-disabled",
      "err-disable",
    ],
  },
  { id: "ospf", en: ["ospf", "ospf cost"] },
  { id: "crc", en: ["crc", "crc errors", "crc error"] },
  { id: "arp", en: ["arp", "mac table", "mac address table"] },
  { id: "snmp", en: ["snmp", "mib", "snmp trap", "snmp traps"] },
  { id: "syslog", en: ["syslog"] },
];

export const KNOWLEDGE: KnowledgeEntry[] = [
  {
    id: "tcp-vs-udp",
    covers: ["tcp", "udp"],
    title: { en: "TCP vs UDP", he: "TCP לעומת UDP" },
    summary: {
      en: "**TCP** is connection-oriented: it sets up a session (3-way handshake), numbers every byte, retransmits what is lost and delivers data in order. **UDP** is connectionless: it sends independent datagrams with no handshake, no retransmission and no ordering. TCP trades speed for reliability; UDP trades reliability for low overhead and latency.",
      he: "**TCP** הוא פרוטוקול מבוסס חיבור: הוא פותח שיחה (לחיצת יד משולשת), ממספר כל בית, שולח מחדש מה שאבד ומעביר את הנתונים לפי הסדר. **UDP** אינו מבוסס חיבור: הוא שולח חבילות עצמאיות בלי לחיצת יד, בלי שליחה חוזרת ובלי סדר מובטח. TCP מעדיף אמינות על פני מהירות, ו-UDP מעדיף תקורה ושיהוי נמוכים על פני אמינות.",
    },
    detail: {
      en: "Typical TCP users: HTTP/HTTPS, SSH, SMTP, database connections, file transfer.\nTypical UDP users: DNS queries, DHCP, SNMP, syslog (classic), VoIP/RTP, video streaming, NTP.\n\nTroubleshooting angle: TCP problems show up as retransmissions, resets (RST) and slow handshakes; UDP problems show up as silent loss, because nothing is resent. A firewall rule that allows TCP/53 but not UDP/53 breaks most DNS.",
      he: "שימושים נפוצים ב-TCP: HTTP/HTTPS, SSH, SMTP, חיבורי מסד נתונים, העברת קבצים.\nשימושים נפוצים ב-UDP: שאילתות DNS, DHCP, SNMP, syslog קלאסי, VoIP/RTP, הזרמת וידאו, NTP.\n\nמבחינת איתור תקלות: בעיות TCP נראות כשליחות חוזרות, איפוסים (RST) ולחיצות יד איטיות. בעיות UDP נראות כאובדן שקט, כי שום דבר לא נשלח מחדש. חוק בחומת אש שמתיר TCP/53 אבל לא UDP/53 שובר את רוב ה-DNS.",
    },
  },
  {
    id: "tcp",
    covers: ["tcp"],
    title: { en: "TCP", he: "TCP" },
    summary: {
      en: "**TCP (Transmission Control Protocol)** is a Layer 4 transport protocol that gives applications a reliable, ordered byte stream. It opens a connection with a 3-way handshake (SYN, SYN-ACK, ACK), acknowledges data, retransmits lost segments and controls the sending rate (flow and congestion control).",
      he: "**TCP (Transmission Control Protocol)** הוא פרוטוקול תעבורה בשכבה 4 שנותן לאפליקציות זרם נתונים אמין ומסודר. הוא פותח חיבור בלחיצת יד משולשת (SYN, SYN-ACK, ACK), מאשר קבלת נתונים, שולח מחדש מקטעים שאבדו ומווסת את קצב השליחה (בקרת זרימה ועומס).",
    },
    detail: {
      en: "Key fields: source/destination port, sequence and acknowledgment numbers, flags (SYN, ACK, FIN, RST), window size.\nCommon issues: retransmissions (loss or congestion), zero window (receiver overloaded), RST (port closed or firewall reject), long handshake time (latency or a slow server).",
      he: "שדות מרכזיים: פורט מקור ויעד, מספרי רצף ואישור, דגלים (SYN, ACK, FIN, RST), גודל חלון.\nתקלות נפוצות: שליחות חוזרות (אובדן או עומס), חלון אפס (המקבל עמוס), RST (פורט סגור או דחייה בחומת אש), לחיצת יד ארוכה (שיהוי או שרת איטי).",
    },
  },
  {
    id: "udp",
    covers: ["udp"],
    title: { en: "UDP", he: "UDP" },
    summary: {
      en: "**UDP (User Datagram Protocol)** is a Layer 4 transport protocol that sends independent datagrams with an 8-byte header: ports, length and checksum. There is no connection setup, acknowledgment, retransmission or ordering, so it is fast and light but unreliable.",
      he: "**UDP (User Datagram Protocol)** הוא פרוטוקול תעבורה בשכבה 4 ששולח חבילות עצמאיות עם כותרת של 8 בתים: פורטים, אורך ו-checksum. אין הקמת חיבור, אישורים, שליחה חוזרת או סדר, ולכן הוא מהיר וקל אבל לא אמין.",
    },
    detail: {
      en: "Used where speed matters more than perfect delivery, or where the application handles reliability itself: DNS, DHCP, SNMP, NTP, VoIP, streaming, QUIC (HTTP/3).\nTroubleshooting: loss is silent, so check interface drops, QoS and firewall rules; a capture shows requests with no replies.",
      he: "משמש כשמהירות חשובה יותר ממסירה מושלמת, או כשהאפליקציה דואגת לאמינות בעצמה: DNS, DHCP, SNMP, NTP, VoIP, הזרמה, QUIC (HTTP/3).\nאיתור תקלות: אובדן הוא שקט, לכן בודקים השלכות בממשקים, QoS וחוקי חומת אש. בהקלטת תעבורה רואים בקשות בלי תשובות.",
    },
  },
  {
    id: "dns",
    covers: ["dns"],
    title: { en: "DNS", he: "DNS" },
    summary: {
      en: "**DNS (Domain Name System)** translates names such as server01.corp.local into IP addresses. A client asks a resolver (usually over UDP/53); the resolver answers from cache or walks the hierarchy (root → TLD → authoritative server) and returns records such as A/AAAA (address), CNAME (alias), MX (mail) and PTR (reverse lookup).",
      he: "**DNS (Domain Name System)** מתרגם שמות כמו server01.corp.local לכתובות IP. הלקוח שואל שרת פענוח (בדרך כלל ב-UDP/53), והשרת עונה מהמטמון או עובר על ההיררכיה (שורש ← סיומת ← שרת סמכותי) ומחזיר רשומות כמו A/AAAA (כתובת), CNAME (כינוי), MX (דואר) ו-PTR (חיפוש הפוך).",
    },
    detail: {
      en: "On a closed network, internal DNS servers are authoritative for internal zones, and there is usually no forwarding to the internet.\nCommon issues: wrong or unreachable DNS server in DHCP options, stale cache (TTL), a missing PTR record breaking logging or authentication, UDP/53 blocked while TCP/53 is open (large responses and zone transfers use TCP).\nUseful checks: nslookup / dig against a specific server, compare answers from two servers, check the TTL.",
      he: "ברשת סגורה, שרתי DNS פנימיים הם הסמכותיים לאזורים הפנימיים, ובדרך כלל אין העברה לאינטרנט.\nתקלות נפוצות: שרת DNS שגוי או לא זמין באפשרויות DHCP, מטמון ישן (TTL), רשומת PTR חסרה ששוברת לוגים או אימות, UDP/53 חסום כש-TCP/53 פתוח (תשובות גדולות והעברות אזור עוברות ב-TCP).\nבדיקות שימושיות: nslookup או dig מול שרת מסוים, השוואת תשובות משני שרתים, בדיקת ה-TTL.",
    },
  },
  {
    id: "dhcp",
    covers: ["dhcp"],
    title: { en: "DHCP", he: "DHCP" },
    summary: {
      en: "**DHCP (Dynamic Host Configuration Protocol)** hands out IP settings automatically: address, subnet mask, default gateway, DNS servers and lease time. The exchange is DORA: Discover, Offer, Request, Acknowledge (UDP 67/68).",
      he: "**DHCP (Dynamic Host Configuration Protocol)** מחלק הגדרות IP אוטומטית: כתובת, מסכת רשת, שער ברירת מחדל, שרתי DNS וזמן חכירה. התהליך נקרא DORA: Discover, Offer, Request, Acknowledge (UDP 67/68).",
    },
    detail: {
      en: "Clients in another VLAN reach the server through a relay (ip helper-address) on the router or Layer 3 switch.\nCommon issues: exhausted scope, missing relay on a new VLAN, a rogue DHCP server (blocked with DHCP snooping), wrong gateway or DNS option. A client with a 169.254.x.x address got no DHCP answer.",
      he: "לקוחות ב-VLAN אחר מגיעים לשרת דרך ממסר (ip helper-address) בנתב או במתג שכבה 3.\nתקלות נפוצות: מאגר כתובות שנגמר, ממסר חסר ב-VLAN חדש, שרת DHCP זר (נחסם עם DHCP snooping), אפשרות שער או DNS שגויה. לקוח עם כתובת 169.254.x.x לא קיבל תשובת DHCP.",
    },
  },
  {
    id: "switch-vs-router",
    covers: ["switch", "router"],
    title: { en: "Switch vs router", he: "מתג לעומת נתב" },
    summary: {
      en: "A **switch** forwards Ethernet frames **inside** a network (Layer 2), using a MAC address table to send each frame only to the right port. A **router** forwards IP packets **between** networks (Layer 3), using a routing table to choose the next hop. In short: switches connect devices in the same LAN or VLAN; routers connect different networks and subnets.",
      he: "**מתג** מעביר מסגרות Ethernet **בתוך** רשת (שכבה 2), בעזרת טבלת כתובות MAC, ושולח כל מסגרת רק לפורט הנכון. **נתב** מעביר חבילות IP **בין** רשתות (שכבה 3), בעזרת טבלת ניתוב, ובוחר את הקפיצה הבאה. בקיצור: מתגים מחברים מכשירים באותה רשת מקומית או VLAN, ונתבים מחברים בין רשתות ותתי-רשתות שונות.",
    },
    detail: {
      en: 'Layer 3 switches blur the line: they switch at line rate and also route between VLANs (SVIs), but usually lack WAN interfaces, NAT and large routing tables.\nWhen troubleshooting: "same VLAN can talk, other VLANs can\'t" points to routing or the gateway; "nothing on this port works" points to the switch port (VLAN, STP, err-disabled).',
      he: 'מתגי שכבה 3 מטשטשים את ההבדל: הם מעבירים במהירות קו וגם מנתבים בין VLANים (SVI), אבל בדרך כלל אין להם ממשקי WAN, NAT וטבלאות ניתוב גדולות.\nבאיתור תקלות: "באותו VLAN יש תקשורת, ל-VLAN אחר אין" מצביע על ניתוב או על השער. "שום דבר לא עובד בפורט הזה" מצביע על פורט המתג (VLAN, STP, err-disabled).',
    },
  },
  {
    id: "switch",
    covers: ["switch"],
    title: { en: "Network switch", he: "מתג רשת" },
    summary: {
      en: "A **switch** is a Layer 2 device that connects hosts in the same network. It learns which MAC address sits behind which port and forwards each frame only where it needs to go. Managed switches add VLANs, trunks, spanning tree, port security and monitoring (SNMP, syslog).",
      he: "**מתג** הוא רכיב בשכבה 2 שמחבר מכשירים באותה רשת. הוא לומד איזו כתובת MAC נמצאת מאחורי כל פורט, ומעביר כל מסגרת רק לאן שהיא צריכה להגיע. מתגים מנוהלים מוסיפים VLANים, trunkים, Spanning Tree, אבטחת פורטים וניטור (SNMP, syslog).",
    },
    detail: {
      en: "Access ports carry one VLAN to an end device; trunk ports carry many VLANs (802.1Q tags) between switches.\nCommon issues: wrong access VLAN, VLAN missing from a trunk, err-disabled port (BPDU Guard, port security), duplex mismatch, STP loop or topology change.",
      he: "פורט access מעביר VLAN אחד למכשיר קצה. פורט trunk מעביר כמה VLANים (תגיות 802.1Q) בין מתגים.\nתקלות נפוצות: VLAN שגוי בפורט, VLAN חסר ב-trunk, פורט err-disabled (BPDU Guard, אבטחת פורט), אי-התאמת duplex, לולאת STP או שינוי טופולוגיה.",
    },
  },
  {
    id: "router",
    covers: ["router"],
    title: { en: "Router", he: "נתב" },
    summary: {
      en: "A **router** is a Layer 3 device that forwards IP packets between networks. It picks the best path from its routing table, which is built from connected networks, static routes and routing protocols such as OSPF and BGP.",
      he: "**נתב** הוא רכיב בשכבה 3 שמעביר חבילות IP בין רשתות. הוא בוחר את המסלול הטוב ביותר מטבלת הניתוב, שנבנית מרשתות מחוברות, מסלולים סטטיים ופרוטוקולי ניתוב כמו OSPF ו-BGP.",
    },
    detail: {
      en: "Route selection: longest prefix match first, then administrative distance, then the protocol metric (for example OSPF cost).\nCommon issues: missing or wrong route, neighbor adjacency down, asymmetric routing through a firewall, saturated or erroring WAN link.",
      he: "בחירת מסלול: קודם ההתאמה הארוכה ביותר לקידומת, אחר כך מרחק מנהלי, ואז מדד הפרוטוקול (למשל עלות OSPF).\nתקלות נפוצות: מסלול חסר או שגוי, שכנות שנפלה, ניתוב א-סימטרי דרך חומת אש, קו WAN עמוס או עם שגיאות.",
    },
  },
  {
    id: "osi",
    covers: ["osi"],
    title: { en: "OSI model", he: "מודל OSI" },
    summary: {
      en: "The **OSI model** splits network communication into 7 layers: 1 Physical (cables, optics), 2 Data Link (Ethernet, MAC, switches), 3 Network (IP, routers), 4 Transport (TCP/UDP, ports), 5 Session, 6 Presentation (encoding, encryption), 7 Application (HTTP, DNS, SNMP).",
      he: "**מודל OSI** מחלק תקשורת רשת ל-7 שכבות: 1 פיזית (כבלים, סיבים), 2 קו נתונים (Ethernet, MAC, מתגים), 3 רשת (IP, נתבים), 4 תעבורה (TCP/UDP, פורטים), 5 שיחה, 6 ייצוג (קידוד, הצפנה), 7 יישום (HTTP, DNS, SNMP).",
    },
    detail: {
      en: "Troubleshooting bottom-up is the classic use: link light and errors (L1), VLAN and MAC learning (L2), IP and routing (L3), ports and firewall rules (L4), then the application (L7). In MoniComm terms, L0 is the physical plant itself: patch panels, cabinets and fiber.",
      he: "השימוש הקלאסי הוא איתור תקלות מלמטה למעלה: נורית קישור ושגיאות (שכבה 1), VLAN ולמידת MAC (שכבה 2), IP וניתוב (שכבה 3), פורטים וחוקי חומת אש (שכבה 4), ואז האפליקציה (שכבה 7). במונחי MoniComm, שכבה 0 היא התשתית הפיזית עצמה: לוחות ניתוב, ארונות וסיבים.",
    },
  },
  {
    id: "vlan",
    covers: ["vlan"],
    title: { en: "VLAN", he: "VLAN" },
    summary: {
      en: "A **VLAN** splits one physical switch network into separate Layer 2 broadcast domains. Hosts in different VLANs can only talk through a router or Layer 3 switch. Trunk links carry several VLANs using 802.1Q tags.",
      he: "**VLAN** מחלק רשת מתגים פיזית אחת לכמה תחומי שידור נפרדים בשכבה 2. מכשירים ב-VLANים שונים מתקשרים רק דרך נתב או מתג שכבה 3. קישורי trunk מעבירים כמה VLANים בעזרת תגיות 802.1Q.",
    },
    detail: {
      en: "Common issues: access port in the wrong VLAN, VLAN not allowed on the trunk, native VLAN mismatch, missing SVI or DHCP relay for a new VLAN.",
      he: "תקלות נפוצות: פורט access ב-VLAN שגוי, VLAN שלא מותר ב-trunk, אי-התאמה ב-native VLAN, SVI או ממסר DHCP חסרים ל-VLAN חדש.",
    },
  },
  {
    id: "stp",
    covers: ["stp"],
    title: { en: "Spanning Tree and BPDU Guard", he: "Spanning Tree ו-BPDU Guard" },
    summary: {
      en: "**Spanning Tree (STP)** prevents Layer 2 loops by blocking redundant paths; switches exchange BPDUs to agree on the topology. **BPDU Guard** protects edge ports: if a BPDU arrives on a port meant for a PC, the switch puts it in **err-disabled** state, because it means another switch was plugged in.",
      he: "**Spanning Tree (STP)** מונע לולאות בשכבה 2 על ידי חסימת מסלולים כפולים. המתגים מחליפים ביניהם BPDUs כדי להסכים על הטופולוגיה. **BPDU Guard** מגן על פורטי קצה: אם מגיע BPDU לפורט שמיועד למחשב, המתג מעביר אותו למצב **err-disabled**, כי זה סימן שחובר אליו מתג נוסף.",
    },
    detail: {
      en: "Recovery: remove the device that sent BPDUs, then shutdown / no shutdown the port, or let errdisable recovery bring it back after a timer. If the cause is still connected, the port goes down again.\nWhy it matters: an unmanaged switch or a looped cable on an access port can cause a broadcast storm that takes down the whole VLAN.",
      he: "שחזור: מנתקים את המכשיר ששלח BPDUs, ואז מבצעים shutdown / no shutdown לפורט, או נותנים ל-errdisable recovery להחזיר אותו אחרי טיימר. אם הגורם עדיין מחובר, הפורט ייפול שוב.\nלמה זה חשוב: מתג לא מנוהל או כבל בלולאה בפורט access יכולים לגרום לסערת שידורים שמפילה את כל ה-VLAN.",
    },
  },
  {
    id: "ospf",
    covers: ["ospf"],
    title: { en: "OSPF and OSPF cost", he: "OSPF ועלות OSPF" },
    summary: {
      en: "**OSPF** is a link-state routing protocol: routers in an area share their link states and each one computes shortest paths. The **cost** of each interface (lower is better) decides which path wins. Raising a link's cost is a common, reversible way to steer traffic onto a backup path.",
      he: "**OSPF** הוא פרוטוקול ניתוב מסוג link-state: הנתבים באזור משתפים את מצב הקישורים שלהם, וכל אחד מחשב את המסלולים הקצרים ביותר. **העלות** של כל ממשק (נמוכה יותר עדיפה) קובעת איזה מסלול נבחר. העלאת העלות של קישור היא דרך נפוצה והפיכה להעביר תעבורה למסלול גיבוי.",
    },
    detail: {
      en: "Neighbor states go Down → Init → 2-Way → ExStart → Exchange → Loading → Full. A neighbor stuck below Full, or flapping, usually means MTU, timers, authentication or a link problem.\nChanging cost causes a short reconvergence, so a confirmed commit with auto-rollback is the safe way to do it on a router.",
      he: "מצבי שכנות: Down ← Init ← 2-Way ← ExStart ← Exchange ← Loading ← Full. שכן שתקוע מתחת ל-Full או מהבהב מעיד בדרך כלל על MTU, טיימרים, אימות או בעיית קישור.\nשינוי עלות גורם להתכנסות קצרה מחדש, ולכן הדרך הבטוחה לבצע אותו בנתב היא commit מאושר עם חזרה אוטומטית.",
    },
  },
  {
    id: "crc",
    covers: ["crc"],
    title: { en: "CRC errors", he: "שגיאות CRC" },
    summary: {
      en: "**CRC errors** count frames that arrived damaged: the checksum at the end of the frame didn't match. They are almost always physical (Layer 1): a dirty or failing optic, bad fiber or cable, a loose connector or electrical interference.",
      he: "**שגיאות CRC** סופרות מסגרות שהגיעו פגומות: ה-checksum בסוף המסגרת לא התאים. כמעט תמיד הן פיזיות (שכבה 1): סיב אופטי או משדר מלוכלכים או תקולים, כבל פגום, מחבר רופף או הפרעה חשמלית.",
    },
    detail: {
      en: "Check: optic receive power (DOM), clean or replace the patch cord and optic, and compare the error counters on both ends of the link. Rising CRCs on a busy link cause retransmissions and lower throughput long before the link actually goes down.",
      he: "מה בודקים: עוצמת הקליטה של המשדר (DOM), ניקוי או החלפה של כבל המגשר והמשדר, והשוואת מוני השגיאות בשני צידי הקישור. שגיאות CRC שעולות בקישור עמוס גורמות לשליחות חוזרות ולירידה בתפוקה הרבה לפני שהקישור נופל בפועל.",
    },
  },
  {
    id: "arp",
    covers: ["arp"],
    title: { en: "ARP and the MAC table", he: "ARP וטבלת MAC" },
    summary: {
      en: '**ARP** maps an IP address to a MAC address inside a subnet; routers and hosts keep an ARP table. Switches keep a **MAC address table** that says which port each MAC was learned on. Together they answer "which switch port is this IP on?"',
      he: '**ARP** ממפה כתובת IP לכתובת MAC בתוך תת-רשת, ונתבים ומחשבים שומרים טבלת ARP. מתגים שומרים **טבלת כתובות MAC** שאומרת באיזה פורט נלמדה כל כתובת. יחד הן עונות על השאלה "באיזה פורט במתג נמצאת כתובת ה-IP הזו?"',
    },
    detail: {
      en: "Lookup path: IP → MAC from the gateway's ARP table → port from the switch MAC table → follow LLDP/CDP neighbors until you reach an access port. That is what MoniComm's Mapper automates.",
      he: "מסלול החיפוש: IP ← MAC מטבלת ה-ARP של השער ← פורט מטבלת ה-MAC של המתג ← מעקב אחר שכני LLDP/CDP עד שמגיעים לפורט access. זה מה שה-Mapper של MoniComm עושה אוטומטית.",
    },
  },
  {
    id: "snmp",
    covers: ["snmp"],
    title: { en: "SNMP", he: "SNMP" },
    summary: {
      en: "**SNMP** lets a monitoring server read counters and state from network devices (polling, UDP/161) and lets devices report events on their own (traps and informs, UDP/162). Values are identified by OIDs defined in MIBs. SNMPv3 adds authentication and encryption.",
      he: "**SNMP** מאפשר לשרת ניטור לקרוא מונים ומצבים מרכיבי רשת (תשאול, UDP/161), ומאפשר לרכיבים לדווח על אירועים בעצמם (traps ו-informs, UDP/162). הערכים מזוהים לפי OIDs שמוגדרים ב-MIBs. SNMPv3 מוסיף אימות והצפנה.",
    },
    detail: {
      en: "In MoniComm, SNMP polling and traps run on the separate SNMP server; the Monicomm host never talks to devices directly. Informs are preferred over traps because they are acknowledged and retried.",
      he: "ב-MoniComm, תשאול SNMP וקליטת traps רצים על שרת ה-SNMP הנפרד, ושרת Monicomm אף פעם לא מדבר עם הרכיבים ישירות. מעדיפים informs על פני traps, כי הם מאושרים ונשלחים שוב אם לא התקבלו.",
    },
  },
  {
    id: "syslog",
    covers: ["syslog"],
    title: { en: "Syslog", he: "Syslog" },
    summary: {
      en: "**Syslog** is the standard way devices send log messages to a central server (UDP or TCP 514, or TLS 6514). Each message carries a facility, a severity from 0 (emergency) to 7 (debug), a timestamp, the host and the text.",
      he: "**Syslog** היא הדרך הסטנדרטית שבה רכיבים שולחים הודעות לוג לשרת מרכזי (UDP או TCP בפורט 514, או TLS ב-6514). כל הודעה כוללת facility, רמת חומרה מ-0 (חירום) עד 7 (דיבאג), חותמת זמן, שם הרכיב והטקסט.",
    },
    detail: {
      en: "Accurate time (NTP) on every device is what makes syslog useful for root cause: without it, events from different devices can't be put in order. Cisco messages look like %FACILITY-SEVERITY-MNEMONIC; Junos uses tags like SNMP_TRAP_LINK_DOWN.",
      he: "זמן מדויק (NTP) בכל רכיב הוא מה שהופך את syslog לשימושי לניתוח גורם שורש: בלעדיו אי אפשר לסדר לפי הזמן אירועים מרכיבים שונים. הודעות Cisco נראות כמו %FACILITY-SEVERITY-MNEMONIC, ו-Junos משתמש בתגיות כמו SNMP_TRAP_LINK_DOWN.",
    },
  },
];

/** Best entries for a set of concepts: a comparison entry when one covers them all, else one entry per concept. */
export function lookup(concepts: string[]): KnowledgeEntry[] {
  if (concepts.length === 0) return [];
  if (concepts.length >= 2) {
    const comparison = KNOWLEDGE.find(
      (e) => e.covers.length >= 2 && concepts.slice(0, 2).every((c) => e.covers.includes(c)),
    );
    if (comparison) return [comparison];
  }
  return concepts
    .map((c) => KNOWLEDGE.find((e) => e.covers.length === 1 && e.covers[0] === c))
    .filter((e): e is KnowledgeEntry => Boolean(e))
    .slice(0, 2);
}

export function entryById(id: string): KnowledgeEntry | undefined {
  return KNOWLEDGE.find((e) => e.id === id);
}
