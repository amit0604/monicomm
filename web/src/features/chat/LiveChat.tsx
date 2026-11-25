import { RotateCw, Send, Sparkles, SquarePen, TriangleAlert } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useText } from "../../text";
import { DemoBadge } from "../dashboard/parts";
import "../dashboard/dashboard.css";
import "./live-chat.css";

// Mirrors api/app/modules/chat/service.py.
interface Counts {
  devices: number;
  alerts: number;
  events: number;
}
interface Answer {
  source: "demo" | "live";
  reply: string;
  model: string;
  context: { collected_at: string; included: Counts; totals: Counts };
}
interface Turn {
  question: string;
  answer: Answer;
}

const STORE = "chatiaf-live";
const MAX_CHARS = 2000;
const HISTORY_TURNS = 10; // the server keeps no more than this
const ERRORS = ["no_data_source", "not_allowed", "llm_unavailable"] as const;
type ErrorCode = (typeof ERRORS)[number] | "failed";

/** The conversation lives in this browser tab: it survives moving between modules, not closing the tab. */
function load(): Turn[] {
  try {
    const turns: unknown = JSON.parse(sessionStorage.getItem(STORE) ?? "[]");
    return Array.isArray(turns) ? (turns as Turn[]) : [];
  } catch {
    return [];
  }
}

export function LiveChat() {
  const { t, absolute } = useText();
  const [turns, setTurns] = useState<Turn[]>(load);
  const [text, setText] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<ErrorCode | null>(null);
  const request = useRef<AbortController | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const busy = pending !== null && error === null;

  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "end" });
  }, [turns, pending, error]);
  useEffect(() => {
    try {
      sessionStorage.setItem(STORE, JSON.stringify(turns));
    } catch {
      // Not remembered across modules; the open conversation still works.
    }
  }, [turns]);

  async function ask(question: string) {
    const abort = new AbortController();
    request.current = abort;
    setPending(question);
    setError(null);
    let code: ErrorCode = "failed";
    try {
      const history = turns.slice(-HISTORY_TURNS).flatMap((x) => [
        { role: "user", content: x.question },
        { role: "assistant", content: x.answer.reply },
      ]);
      const res = await fetch("/api/v1/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ messages: [...history, { role: "user", content: question }] }),
        signal: abort.signal,
      });
      const body = (await res.json()) as Answer & { detail?: string };
      if (abort.signal.aborted) return;
      if (res.ok) {
        setTurns([...turns, { question, answer: body }]);
        setPending(null);
        return;
      }
      code = ERRORS.find((e) => e === body.detail) ?? "failed";
    } catch {
      if (abort.signal.aborted) return;
    }
    setError(code);
  }

  function submit(e?: FormEvent) {
    e?.preventDefault();
    const question = text.trim();
    if (!question || busy) return;
    setText("");
    void ask(question);
  }

  function reset() {
    request.current?.abort();
    setTurns([]);
    setPending(null);
    setError(null);
  }

  return (
    <div className="chat">
      <div className="dash__bar">
        <strong>ChatIAF</strong>
        <span className="muted">{t("c_readonly")}</span>
        {(turns.length > 0 || pending) && (
          <button type="button" className="button push" onClick={reset}>
            <SquarePen size={16} aria-hidden="true" />
            {t("c_new")}
          </button>
        )}
      </div>

      <div className="chat__log" role="log" aria-live="polite">
        {turns.length === 0 && !pending && (
          <div className="state">
            <strong>{t("c_empty")}</strong>
            <div className="chat__suggestions">
              {(["c_suggest_1", "c_suggest_2", "c_suggest_3"] as const).map((key) => (
                <button key={key} type="button" className="button" onClick={() => void ask(t(key))}>
                  {t(key)}
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map(({ question, answer: a }, i) => (
          <div key={i} className="chat__turn">
            <div className="bubble bubble--user" dir="auto">
              {question}
            </div>
            <div className="bubble bubble--ai">
              <div className="dash__bar">
                <span className="chat__tag">
                  <Sparkles size={12} aria-hidden="true" />
                  AI
                </span>
                {a.source === "demo" && <DemoBadge />}
              </div>
              <div className="chat__reply" dir="auto">
                {a.reply}
              </div>
              <footer className="chat__sources">
                <strong>{t("c_sources")}:</strong>{" "}
                {(["devices", "alerts", "events"] as const).map((k) => (
                  <span key={k}>
                    {t(`c_${k}`)}{" "}
                    <bdi>
                      {a.context.included[k]}/{a.context.totals[k]}
                    </bdi>
                    {" · "}
                  </span>
                ))}
                {t("c_collected")} <bdi>{absolute(a.context.collected_at)}</bdi> ·{" "}
                <bdi>{a.model}</bdi>
              </footer>
            </div>
          </div>
        ))}
        {pending && (
          <div className="chat__turn">
            <div className="bubble bubble--user" dir="auto">
              {pending}
            </div>
            {error ? (
              <div className="bubble bubble--ai" role="alert">
                <p className="banner">
                  <TriangleAlert size={16} aria-hidden="true" />
                  {t(`e_${error}`)}
                </p>
                <button type="button" className="button" onClick={() => void ask(pending)}>
                  <RotateCw size={16} aria-hidden="true" />
                  {t("retry")}
                </button>
              </div>
            ) : (
              <div className="bubble bubble--ai muted" role="status">
                {t("c_thinking")}
              </div>
            )}
          </div>
        )}
        <div ref={end} className="chat__end" />
      </div>

      <form className="chat__composer" onSubmit={submit}>
        <textarea
          className="field"
          aria-label={t("c_placeholder")}
          placeholder={t("c_placeholder")}
          dir={text ? "auto" : undefined}
          rows={2}
          maxLength={MAX_CHARS}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button className="button button--primary" disabled={busy || !text.trim()}>
          <Send size={16} aria-hidden="true" />
          {t("c_send")}
        </button>
      </form>
      <p className="tile__note">{t("c_notice")}</p>
    </div>
  );
}
