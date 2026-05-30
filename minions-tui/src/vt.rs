//! Render a `capture-pane -e` snapshot (raw ANSI/SGR bytes) into styled
//! ratatui lines using the vt100 parser. This is how the operator sees a
//! role's real screen inside a TUI pane without attaching.

use ratatui::style::{Color, Modifier, Style};
use ratatui::text::{Line, Span};

/// Parse ANSI bytes into ratatui Lines sized to (rows, cols). The vt100 parser
/// interprets SGR colors/attrs; we lift each cell's fg/bg/attrs into a Span.
pub fn ansi_to_lines(raw: &str, rows: u16, cols: u16) -> Vec<Line<'static>> {
    let rows = rows.max(1);
    let cols = cols.max(1);
    let mut parser = vt100::Parser::new(rows, cols, 0);
    // `tmux capture-pane` emits LF-only line breaks. A vt100 emulator treats
    // bare LF as "move down one row" WITHOUT returning to column 0, so each
    // captured line would start where the previous ended (a rightward
    // staircase). Normalize LF → CRLF so every line break also carries a
    // carriage return. (Existing CRs are left intact — we only add a CR
    // before an LF that doesn't already have one.)
    let normalized = normalize_newlines(raw);
    parser.process(normalized.as_bytes());
    let screen = parser.screen();

    let mut lines = Vec::with_capacity(rows as usize);
    for row in 0..rows {
        let mut spans: Vec<Span<'static>> = Vec::new();
        let mut cur = String::new();
        let mut cur_style: Option<Style> = None;

        for col in 0..cols {
            let (ch, style) = match screen.cell(row, col) {
                Some(cell) => {
                    let s = cell_style(cell);
                    let c = cell.contents();
                    let c = if c.is_empty() { " ".to_string() } else { c };
                    (c, s)
                }
                None => (" ".to_string(), Style::default()),
            };
            if cur_style == Some(style) {
                cur.push_str(&ch);
            } else {
                if let Some(st) = cur_style.take() {
                    spans.push(Span::styled(std::mem::take(&mut cur), st));
                }
                cur = ch;
                cur_style = Some(style);
            }
        }
        if let Some(st) = cur_style.take() {
            spans.push(Span::styled(cur, st));
        }
        lines.push(Line::from(spans));
    }
    lines
}

fn cell_style(cell: &vt100::Cell) -> Style {
    let mut style = Style::default()
        .fg(conv_color(cell.fgcolor()))
        .bg(conv_color(cell.bgcolor()));
    if cell.bold() {
        style = style.add_modifier(Modifier::BOLD);
    }
    if cell.italic() {
        style = style.add_modifier(Modifier::ITALIC);
    }
    if cell.underline() {
        style = style.add_modifier(Modifier::UNDERLINED);
    }
    if cell.inverse() {
        style = style.add_modifier(Modifier::REVERSED);
    }
    style
}

fn conv_color(c: vt100::Color) -> Color {
    match c {
        vt100::Color::Default => Color::Reset,
        vt100::Color::Idx(i) => Color::Indexed(i),
        vt100::Color::Rgb(r, g, b) => Color::Rgb(r, g, b),
    }
}

/// Turn LF-only line breaks into CRLF so the vt100 emulator resets to column 0
/// on each new line (no rightward staircase). A LF already preceded by CR is
/// left as-is.
fn normalize_newlines(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + s.len() / 40 + 8);
    let mut prev = '\0';
    for ch in s.chars() {
        if ch == '\n' && prev != '\r' {
            out.push('\r');
        }
        out.push(ch);
        prev = ch;
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use ratatui::style::Modifier;

    #[test]
    fn plain_text_renders_one_span_per_row() {
        let lines = ansi_to_lines("hello", 1, 10);
        assert_eq!(lines.len(), 1);
        // Whole row collapses to a single styled run since style is uniform.
        let text: String = lines[0].spans.iter().map(|s| s.content.as_ref()).collect();
        assert!(text.starts_with("hello"));
    }

    #[test]
    fn green_sgr_becomes_green_span() {
        // \x1b[32m = green fg, matches what `capture-pane -e` emits.
        let lines = ansi_to_lines("\x1b[32mGO\x1b[39m", 1, 5);
        let green = lines[0]
            .spans
            .iter()
            .find(|s| s.content.contains('G'))
            .expect("a span containing G");
        assert_eq!(green.style.fg, Some(Color::Indexed(2)));
    }

    #[test]
    fn bold_attribute_is_lifted() {
        let lines = ansi_to_lines("\x1b[1mB\x1b[0m", 1, 3);
        let bold = lines[0]
            .spans
            .iter()
            .find(|s| s.content.contains('B'))
            .expect("a span containing B");
        assert!(bold.style.add_modifier.contains(Modifier::BOLD));
    }

    #[test]
    fn rows_are_clamped_to_request() {
        let lines = ansi_to_lines("a\nb\nc", 2, 4);
        assert_eq!(lines.len(), 2, "must produce exactly `rows` lines");
    }

    #[test]
    fn lf_only_does_not_staircase() {
        // Two LF-separated lines must each start at column 0 (no rightward
        // drift). Row 1 should begin with 'b', not be pushed right by row 0.
        let lines = ansi_to_lines("aaa\nb", 2, 8);
        let row1: String = lines[1].spans.iter().map(|s| s.content.as_ref()).collect();
        assert!(row1.starts_with('b'), "row 1 should start at col 0, got {row1:?}");
    }
}

