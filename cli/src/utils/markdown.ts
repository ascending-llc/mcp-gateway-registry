/**
 * Render markdown to terminal-friendly format
 * Simple cleanup for terminal display - doesn't do heavy rendering
 */
export function renderMarkdown(markdown: string): string {
  try {
    let text = markdown;

    // Render tables before other processing
    text = renderMarkdownTables(text);

    // Remove markdown headers but keep the text
    text = text.replace(/^#{1,6}\s+/gm, '');

    // Remove bold/italic markers
    text = text.replace(/\*\*(.+?)\*\*/g, '$1');
    text = text.replace(/\*(.+?)\*/g, '$1');
    text = text.replace(/_(.+?)_/g, '$1');

    // Keep code blocks simple - just remove the markers
    text = text.replace(/```(\w+)?\n([\s\S]*?)```/g, (_match, _lang, code) => {
      return `\n${code.trim()}\n`;
    });

    // Keep inline code with special markers for highlighting
    // Using ANSI-style markers that Ink will preserve
    text = text.replace(/`([^`]+)`/g, '`$1`');

    // Links - show just the text
    text = text.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');

    return text;
  } catch (error) {
    // Fallback to plain text if parsing fails
    return markdown;
  }
}

/**
 * Render markdown tables to a cleaner terminal format
 */
function renderMarkdownTables(text: string): string {
  // Match markdown tables (header row, separator row, and data rows)
  // Allow leading whitespace before the table
  const tableRegex = /^[ \t]*(\|.+\|)[ \t]*\n[ \t]*(\|(?:[\s:-]+\|)+)[ \t]*\n((?:[ \t]*\|.+\|[ \t]*\n?)*)/gm;

  return text.replace(tableRegex, (_match, headerRow, _separatorRow, dataRows) => {
    const parseRow = (row: string): string[] => {
      return row
        .split('|')
        .map(cell => cell.trim())
        .filter(cell => cell.length > 0);
    };

    const headers = parseRow(headerRow);
    const rows = dataRows
      .trim()
      .split('\n')
      .filter((row: string) => row.trim().length > 0)
      .map(parseRow);

    // Calculate column widths
    const columnWidths = headers.map((header, i) => {
      const maxDataWidth = Math.max(...rows.map((row: string[]) => (row[i] || '').length));
      return Math.max(header.length, maxDataWidth);
    });

    // Format a row with proper padding
    const formatRow = (cells: string[]): string => {
      return '  ' + cells.map((cell, i) => {
        const width = columnWidths[i] || 0;
        return cell.padEnd(width, ' ');
      }).join('  |  ');
    };

    // Build the formatted table
    const lines: string[] = [];
    lines.push(''); // Empty line before table
    lines.push(formatRow(headers));
    lines.push('  ' + columnWidths.map((w: number) => '─'.repeat(w)).join('──┼──'));
    rows.forEach((row: string[]) => lines.push(formatRow(row)));
    lines.push(''); // Empty line after table

    return lines.join('\n');
  });
}

/**
 * Check if text contains markdown formatting
 */
export function hasMarkdown(text: string): boolean {
  const markdownPatterns = [
    /^#{1,6}\s/m,           // Headers
    /\*\*.*?\*\*/,          // Bold
    /_.*?_/,                // Italic
    /`.*?`/,                // Inline code
    /```[\s\S]*?```/,       // Code blocks
    /^\s*[-*+]\s/m,         // Lists
    /^\s*\d+\.\s/m,         // Numbered lists
    /\[.*?\]\(.*?\)/,       // Links
  ];

  return markdownPatterns.some(pattern => pattern.test(text));
}

/**
 * Format tool output with syntax highlighting hints
 */
export function formatToolOutput(toolName: string, output: string, isError: boolean = false): string {
  const status = isError ? "✗" : "✓";
  const header = `\n${status} **${toolName}**\n`;

  // Try to parse as JSON for better formatting
  try {
    const parsed = JSON.parse(output);
    return `${header}\`\`\`json\n${JSON.stringify(parsed, null, 2)}\n\`\`\``;
  } catch {
    // Not JSON, return as code block
    return `${header}\`\`\`\n${output}\n\`\`\``;
  }
}
