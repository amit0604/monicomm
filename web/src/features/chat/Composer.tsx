import { SendHorizontal, Square } from "lucide-react";
import { useLayoutEffect, useRef, useState } from "react";
import { Button } from "../../components/ui";
import { useI18n } from "../../i18n";

const MAX_ROWS_HEIGHT = 160;

export function Composer({
  busy,
  onSend,
  onStop,
}: {
  busy: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}) {
  const { t } = useI18n();
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  // Grow with the text, up to a cap, like a messaging app.
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    // Empty: let CSS decide, so a wrapped placeholder in a narrow window never sticks as the height.
    if (!text) {
      el.style.height = "";
      return;
    }
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_ROWS_HEIGHT)}px`;
  }, [text]);

  const submit = () => {
    if (busy || !text.trim()) return;
    onSend(text);
    setText("");
  };

  return (
    <form
      className="composer"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <label htmlFor="chat-input" className="visually-hidden">
        {t("chat.inputLabel")}
      </label>
      <textarea
        id="chat-input"
        ref={ref}
        rows={1}
        value={text}
        placeholder={t("chat.inputPlaceholder")}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
          }
        }}
        dir="auto"
      />
      {busy ? (
        <Button
          variant="secondary"
          onClick={onStop}
          aria-label={t("chat.stop")}
          title={t("chat.stop")}
          iconOnly
        >
          <Square size={16} aria-hidden="true" />
        </Button>
      ) : (
        <Button
          variant="primary"
          type="submit"
          aria-label={t("chat.send")}
          title={t("chat.send")}
          iconOnly
          disabled={!text.trim()}
        >
          <SendHorizontal size={16} aria-hidden="true" className="flip-rtl" />
        </Button>
      )}
    </form>
  );
}
