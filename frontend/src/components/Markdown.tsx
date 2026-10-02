import ReactMarkdown from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkMath from 'remark-math';
import 'katex/dist/katex.min.css';

const BLOCK_MATH = /\\\[([\s\S]+?)\\\]/g; // \[ … \]
const INLINE_MATH = /\\\(([\s\S]+?)\\\)/g; // \( … \)

/**
 * Los modelos escriben fórmulas en LaTeX con \( … \) y \[ … \], pero remark-math
 * no las reconoce. Se convierten a $$…$$ (en línea) y a un bloque $$ … $$.
 * Se desactiva el $ simple para que montos como "$100 y $200" no se lean como fórmula.
 */
export function normalizeMath(text: string): string {
  return text
    .replace(BLOCK_MATH, (_, expr: string) => `\n$$\n${expr.trim()}\n$$\n`)
    .replace(INLINE_MATH, (_, expr: string) => `$$${expr.trim()}$$`);
}

export default function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[[remarkMath, { singleDollarTextMath: false }]]}
      rehypePlugins={[[rehypeKatex, { throwOnError: false }]]}
    >
      {normalizeMath(children)}
    </ReactMarkdown>
  );
}
