// Markdown — a tiny markdown renderer for the lesson cards.
//
// Supports:
//   * `#` / `##` / `###` headings (h1, h2, h3)
//   * `**bold**` and `` `code` `` inline
//   * `- item` unordered lists
//   * blank-line-separated paragraphs
//
// No `react-markdown` dep — keeps the bundle tiny and avoids pulling
// in extra Node-only modules.

import { useMemo } from 'react';

interface MarkdownProps {
  source: string;
}

interface Block {
  kind: 'h1' | 'h2' | 'h3' | 'p' | 'ul';
  text?: string;
  items?: string[];
}

export function Markdown({ source }: MarkdownProps) {
  const blocks = useMemo(() => parseBlocks(source), [source]);
  return (
    <div className="text-xs text-text-secondary">
      {blocks.map((b, i) => {
        if (b.kind === 'h1') {
          return (
            <h1 key={i} className="text-base font-semibold text-text-primary mt-2 mb-1">
              {renderInline(b.text ?? '')}
            </h1>
          );
        }
        if (b.kind === 'h2') {
          return (
            <h2 key={i} className="text-sm font-semibold text-text-primary mt-3 mb-1">
              {renderInline(b.text ?? '')}
            </h2>
          );
        }
        if (b.kind === 'h3') {
          return (
            <h3 key={i} className="text-xs font-semibold text-text-primary mt-2 mb-1">
              {renderInline(b.text ?? '')}
            </h3>
          );
        }
        if (b.kind === 'p') {
          return (
            <p key={i} className="my-1.5 leading-relaxed">
              {renderInline(b.text ?? '')}
            </p>
          );
        }
        if (b.kind === 'ul') {
          return (
            <ul key={i} className="my-1.5 ml-4 list-disc space-y-0.5">
              {(b.items ?? []).map((it, j) => (
                <li key={j}>{renderInline(it)}</li>
              ))}
            </ul>
          );
        }
        return null;
      })}
    </div>
  );
}

// ── parsing ───────────────────────────────────────────────────────

function parseBlocks(src: string): Block[] {
  const out: Block[] = [];
  const lines = src.split('\n');
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === '') {
      i += 1;
      continue;
    }
    const h = line.match(/^(#{1,3})\s+(.*)$/);
    if (h) {
      const level = h[1].length as 1 | 2 | 3;
      out.push({ kind: `h${level}` as Block['kind'], text: h[2] });
      i += 1;
      continue;
    }
    if (line.startsWith('- ')) {
      const items: string[] = [];
      while (i < lines.length && lines[i].startsWith('- ')) {
        items.push(lines[i].slice(2));
        i += 1;
      }
      out.push({ kind: 'ul', items });
      continue;
    }
    // paragraph: collect until blank line / heading / list
    const buf: string[] = [line];
    i += 1;
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !lines[i].match(/^#{1,3}\s/) &&
      !lines[i].startsWith('- ')
    ) {
      buf.push(lines[i]);
      i += 1;
    }
    out.push({ kind: 'p', text: buf.join(' ') });
  }
  return out;
}

// ── inline: **bold** + `code` ──────────────────────────────────────

function renderInline(text: string): React.ReactNode {
  // Tokenise into runs of: code (`...`), bold (**...**), plain.
  const parts: React.ReactNode[] = [];
  let rest = text;
  let key = 0;
  const re = /(`[^`]+`|\*\*[^*]+\*\*)/g;
  let lastIdx = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(rest)) !== null) {
    if (m.index > lastIdx) {
      parts.push(rest.slice(lastIdx, m.index));
    }
    const tok = m[0];
    if (tok.startsWith('`')) {
      parts.push(
        <code key={key++} className="px-1 py-0.5 rounded bg-bg-elevated text-2xs font-mono text-text-primary">
          {tok.slice(1, -1)}
        </code>,
      );
    } else {
      parts.push(<strong key={key++} className="font-semibold text-text-primary">{tok.slice(2, -2)}</strong>);
    }
    lastIdx = m.index + tok.length;
  }
  if (lastIdx < rest.length) {
    parts.push(rest.slice(lastIdx));
  }
  return parts;
}