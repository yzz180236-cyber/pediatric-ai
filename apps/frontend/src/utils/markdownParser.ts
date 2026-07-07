/**
 * 轻量级 Markdown 解析器
 * 支持：**加粗**、*斜体*、`代码`、有序列表、无序列表、标题（#）、段落分隔
 * 专为 Taro 小程序/H5 环境设计，不依赖 DOM
 */

export type MarkdownToken =
  | { type: 'heading'; level: number; children: InlineToken[] }
  | { type: 'paragraph'; children: InlineToken[] }
  | { type: 'ordered_list'; items: InlineToken[][] }
  | { type: 'unordered_list'; items: InlineToken[][] }
  | { type: 'blank' }

export type InlineToken =
  | { type: 'text'; value: string }
  | { type: 'bold'; value: string }
  | { type: 'italic'; value: string }
  | { type: 'code'; value: string }

/** 解析行内 Markdown（**bold**、*italic*、`code`） */
export function parseInline(text: string): InlineToken[] {
  const tokens: InlineToken[] = []
  // 匹配 **bold**、*italic*、`code`
  const re = /(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`)/g
  let last = 0
  let match: RegExpExecArray | null

  while ((match = re.exec(text)) !== null) {
    if (match.index > last) {
      tokens.push({ type: 'text', value: text.slice(last, match.index) })
    }

    if (match[2] !== undefined) {
      tokens.push({ type: 'bold', value: match[2] })
    } else if (match[3] !== undefined) {
      tokens.push({ type: 'italic', value: match[3] })
    } else if (match[4] !== undefined) {
      tokens.push({ type: 'code', value: match[4] })
    }

    last = match.index + match[0].length
  }

  if (last < text.length) {
    tokens.push({ type: 'text', value: text.slice(last) })
  }

  return tokens
}

/** 将 Markdown 字符串解析为块级 Token 列表 */
export function parseMarkdown(markdown: string): MarkdownToken[] {
  const lines = markdown.split('\n')
  const tokens: MarkdownToken[] = []

  let i = 0
  while (i < lines.length) {
    const line = lines[i]

    // 空行
    if (line.trim() === '') {
      i++
      continue
    }

    // 标题 # / ## / ###
    const headingMatch = line.match(/^(#{1,6})\s+(.*)$/)
    if (headingMatch) {
      tokens.push({
        type: 'heading',
        level: headingMatch[1].length,
        children: parseInline(headingMatch[2]),
      })
      i++
      continue
    }

    // 有序列表（以 "1. " 或 "- " 开头，直到非列表行）
    const orderedMatch = line.match(/^(\d+)\.\s+(.*)$/)
    if (orderedMatch) {
      const items: InlineToken[][] = []
      while (i < lines.length && lines[i].match(/^\d+\.\s+/)) {
        const m = lines[i].match(/^\d+\.\s+(.*)$/)!
        items.push(parseInline(m[1]))
        i++
      }
      tokens.push({ type: 'ordered_list', items })
      continue
    }

    // 无序列表（以 "- " 或 "* " 或 "• " 开头）
    const unorderedMatch = line.match(/^[-*•]\s+(.*)$/)
    if (unorderedMatch) {
      const items: InlineToken[][] = []
      while (i < lines.length && lines[i].match(/^[-*•]\s+/)) {
        const m = lines[i].match(/^[-*•]\s+(.*)$/)!
        items.push(parseInline(m[1]))
        i++
      }
      tokens.push({ type: 'unordered_list', items })
      continue
    }

    // 普通段落（将连续非空行合并为一段）
    let paraLines: string[] = []
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !lines[i].match(/^#{1,6}\s/) &&
      !lines[i].match(/^\d+\.\s/) &&
      !lines[i].match(/^[-*•]\s/)
    ) {
      paraLines.push(lines[i])
      i++
    }
    if (paraLines.length > 0) {
      tokens.push({ type: 'paragraph', children: parseInline(paraLines.join(' ')) })
    }
  }

  return tokens
}
