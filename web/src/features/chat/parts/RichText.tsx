import { Fragment } from "react";

/** Renders the tiny subset of markdown the assistant uses: paragraphs, line breaks and **bold**. */
export function RichText({ text }: { text: string }) {
  const paragraphs = text.split(/\n{2,}/).filter((p) => p.trim().length > 0);
  return (
    <>
      {paragraphs.map((paragraph, i) => (
        <p key={i} className="rich-text">
          {paragraph.split("\n").map((line, j) => (
            <Fragment key={j}>
              {j > 0 && <br />}
              {line
                .split(/(\*\*[^*]+\*\*)/g)
                .map((chunk, k) =>
                  chunk.startsWith("**") && chunk.endsWith("**") ? (
                    <strong key={k}>{chunk.slice(2, -2)}</strong>
                  ) : (
                    <Fragment key={k}>{chunk}</Fragment>
                  ),
                )}
            </Fragment>
          ))}
        </p>
      ))}
    </>
  );
}
