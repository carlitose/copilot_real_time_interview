/**
 * Formatta il testo markdown in HTML per la visualizzazione nell'interfaccia chat.
 * 
 * @param text Testo con formattazione markdown
 * @returns HTML formattato
 */
export function formatMarkdown(text: string): string {
  return text
    // Bold
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    // Italic
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    // Code blocks
    .replace(/```([\s\S]*?)```/g, (match, code) => 
      `<pre><code>${code.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</code></pre>`
    )
    // Inline code
    .replace(/`(.*?)`/g, (match, code) =>
      `<code>${code.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</code>`
    )
    // Headers
    .replace(/^# (.*?)$/gm, '<h1>$1</h1>')
    .replace(/^## (.*?)$/gm, '<h2>$1</h2>')
    .replace(/^### (.*?)$/gm, '<h3>$1</h3>')
    // Lists
    .replace(/^- (.*?)$/gm, '<li>$1</li>')
    .replace(/(<li>.*?<\/li>(\n|$))+/g, match => `<ul>${match}</ul>`)
    // Newlines
    .replace(/\n/g, '<br />');
} 