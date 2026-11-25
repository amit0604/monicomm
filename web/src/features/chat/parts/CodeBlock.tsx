import { Check, Copy } from 'lucide-react';
import { useState } from 'react';

function lineClass(line: string, language: string) {
  if (language !== 'diff') return undefined;
  if (line.startsWith('+')) return 'code__line--add';
  if (line.startsWith('-')) return 'code__line--del';
  return undefined;
}

export function CodeBlock({
  title,
  language,
  content,
}: {
  title?: string;
  language: 'cli' | 'diff' | 'log';
  content: string;
}) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard can be blocked on plain-HTTP origins; the text is still selectable.
    }
  };

  return (
    <figure className="code">
      <figcaption className="code__header">
        <span>{title ?? language.toUpperCase()}</span>
        <button type="button" className="code__copy" onClick={copy} aria-label="Copy">
          {copied ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
        </button>
      </figcaption>
      {/* Commands and configs stay left-to-right even in an RTL layout. */}
      <pre dir="ltr">
        {content.split('\n').map((line, i) => (
          <span key={i} className={lineClass(line, language)}>
            {line}
            {'\n'}
          </span>
        ))}
      </pre>
    </figure>
  );
}
