pub mod tui;

const TRAE_AGENT_LOGO: [&str; 6] = [
    "████████┐██████┐  █████┐ ███████┐    █████┐  ██████┐ ███████┐███┐  ██┐████████┐",
    "└──██┌──┘██┌──██┐██┌──██┐██┌────┘   ██┌──██┐██┌────┘ ██┌────┘████┐ ██│└──██┌──┘",
    "   ██│   ██████┌┘███████│█████┐     ███████│██│  ██┐ █████┐  ██┌██┐██│   ██│   ",
    "   ██│   ██┌──██┐██┌──██│██┌──┘     ██┌──██│██│  └██┐██┌──┘  ██│└████│   ██│   ",
    "   ██│   ██│  ██│██│  ██│███████┐   ██│  ██│└██████┌┘███████┐██│ └███│   ██│   ",
    "   └─┘   └─┘  └─┘└─┘  └─┘└──────┘   └─┘  └─┘ └─────┘ └──────┘└─┘  └──┘   └─┘   ",
];

pub fn get_trae_agent_logo() -> String {
    use owo_colors::OwoColorize;

    // Define colors
    let gradient_start = (0x02, 0x74, 0x3B); // 0x02743B
    let gradient_end = (0x32, 0xF0, 0x8C); // 0x32F08C

    // Detect background and choose shadow color accordingly
    let shadow_color = (0x5C, 0xF5, 0xA8); // 0x5CF5A8

    let mut result = String::new();

    for line in TRAE_AGENT_LOGO.iter() {
        let line_length = line.chars().filter(|c| *c == '█').count();
        let mut main_char_index = 0;

        for ch in line.chars() {
            if ch == '█' {
                // Calculate gradient position (0.0 to 1.0)
                let position = if line_length > 1 {
                    main_char_index as f32 / (line_length - 1) as f32
                } else {
                    0.0
                };

                // Interpolate between gradient colors
                let r = (gradient_start.0 as f32
                    + (gradient_end.0 as f32 - gradient_start.0 as f32) * position)
                    as u8;
                let g = (gradient_start.1 as f32
                    + (gradient_end.1 as f32 - gradient_start.1 as f32) * position)
                    as u8;
                let b = (gradient_start.2 as f32
                    + (gradient_end.2 as f32 - gradient_start.2 as f32) * position)
                    as u8;

                result.push_str(&format!("{}", ch.truecolor(r, g, b)));
                main_char_index += 1;
            } else if ch == '└'
                || ch == '┌'
                || ch == '┐'
                || ch == '┘'
                || ch == '─'
                || ch == '│'
                || ch == '┬'
                || ch == '┴'
                || ch == '├'
                || ch == '┤'
                || ch == '┼'
            {
                // Shadow characters
                result.push_str(&format!(
                    "{}",
                    ch.truecolor(shadow_color.0, shadow_color.1, shadow_color.2)
                ));
            } else {
                // Regular characters (spaces, etc.)
                result.push(ch);
            }
        }
        result.push('\n');
    }

    result
}
