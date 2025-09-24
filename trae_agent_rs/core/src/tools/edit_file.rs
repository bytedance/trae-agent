use std::{collections::HashMap, fs};

use crate::{Tool, ToolExecResult};
use thiserror::Error;

const SNIPPET_LINES: usize = 4;
const TAB_WIDTH: usize = 8;

#[derive(Default)]
pub struct EditFile {}

impl Tool for EditFile {
    fn get_name(&self) -> &str {
        "edit_file"
    }

    fn reset(&mut self) {}

    fn get_description(&self) -> &str {
        "Edit an existing file using string replacement or insertion, or create a new file.
        * `replace` command replaces exact string matches with new content
        * `insert` command inserts new content after a specified line number
        * `create` command creates a new file with the specified content
        * The `old_str` parameter should match EXACTLY one or more consecutive lines
        * If the `old_str` parameter is not unique in the file, the replacement will not be performed
        "
    }

    fn get_input_schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to file to edit, e.g. `/repo/file.py`."
                },
                "command": {
                    "type": "string",
                    "description": "The edit command to perform.",
                    "enum": ["replace", "insert", "create"]
                },
                "old_str": {
                    "type": "string",
                    "description": "Required parameter for `replace` command. The exact string to find and replace."
                },
                "new_str": {
                    "type": "string",
                    "description": "Required parameter for all commands. The new string to replace with, insert, or use as file content for create."
                },
                "insert_line": {
                    "type": "integer",
                    "description": "Required parameter for `insert` command. The line number after which to insert the new content (1-based)."
                }
            },
            "required": ["path", "command", "new_str"]
        })
    }

    fn get_descriptive_message(&self, arguments: &HashMap<String, serde_json::Value>) -> String {
        let path = arguments.get("path").and_then(|x| x.as_str()).unwrap_or("");
        match arguments
            .get("command")
            .and_then(|x| x.as_str())
            .unwrap_or("")
        {
            "replace" => format!("Edit file: {}", path),
            "insert" => format!("Insert content into file: {}", path),
            "create" => format!("Create file: {}", path),
            _ => "Unknown file operation".to_string(),
        }
    }

    fn needs_approval(&self, _arguments: &HashMap<String, serde_json::Value>) -> bool {
        false
    }

    fn execute(
        &mut self,
        arguments: HashMap<String, serde_json::Value>,
    ) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<String, String>> + Send + '_>>
    {
        Box::pin(async move {
            let path = arguments.get("path").and_then(|v| v.as_str()).unwrap_or("");
            let command = arguments
                .get("command")
                .and_then(|v| v.as_str())
                .unwrap_or("");

            if path.is_empty() {
                return Err("Path parameter is required".to_string());
            }

            let result = match command {
                "replace" => replace_handler(path, &arguments).await,
                "insert" => insert_handler(path, &arguments).await,
                "create" => create_handler(path, &arguments).await,
                _ => {
                    return Err(format!(
                        "Unknown command: {}. Supported commands are: replace, insert, create",
                        command
                    ));
                }
            };

            match result {
                Ok(tool_result) => {
                    if let Some(error) = tool_result.error
                        && !error.is_empty()
                    {
                        return Err(format!("Error: {}", error));
                    }

                    if let Some(output) = tool_result.output {
                        Ok(output)
                    } else {
                        Ok("Command executed successfully".to_string())
                    }
                }
                Err(e) => Err(format!("Tool execution failed: {}", e)),
            }
        })
    }
}

async fn replace_handler(
    path: &str,
    args: &HashMap<String, serde_json::Value>,
) -> Result<ToolExecResult, EditFileError> {
    let old_str = args.get("old_str").and_then(|v| v.as_str()).unwrap_or("");
    let new_str = args
        .get("new_str")
        .and_then(|v| v.as_str())
        .ok_or(EditFileError::NewStringError)?;

    if old_str.is_empty() {
        return Err(EditFileError::EmptyOldString);
    }

    let mut file_content = fs::read_to_string(path).map_err(|_| EditFileError::Io)?;

    if !file_content.contains(old_str) {
        return Err(EditFileError::OldStringNotExists(path.to_string()));
    }

    // Validate occurrences
    let mut lines_with_hits = Vec::new();
    let mut multiple = false;
    for (idx, line) in file_content.lines().enumerate() {
        let mut from = 0;
        let mut hits_in_line = 0;
        while let Some(pos) = line[from..].find(old_str) {
            hits_in_line += 1;
            from += pos + old_str.len();
            if old_str.is_empty() {
                break;
            }
        }
        if hits_in_line > 0 {
            lines_with_hits.push(idx + 1);
            if hits_in_line > 1 {
                multiple = true;
            }
        }
    }

    if lines_with_hits.len() > 1 || multiple {
        return Err(EditFileError::MultipleOccurrences(
            lines_with_hits[0] as u64,
        ));
    }

    let first_pos_opt = file_content.find(old_str);
    file_content = file_content.replace(old_str, new_str);

    fs::write(path, &file_content).map_err(|_| EditFileError::Io)?;

    let replacement_line: usize = match first_pos_opt {
        Some(pos) => file_content[..pos.min(file_content.len())]
            .bytes()
            .filter(|&b| b == b'\n')
            .count(),
        None => 0,
    };

    let start_line = replacement_line.saturating_sub(SNIPPET_LINES);
    let end_line =
        replacement_line + SNIPPET_LINES + new_str.bytes().filter(|&b| b == b'\n').count();

    let lines: Vec<&str> = file_content.split('\n').collect();
    let end_line_capped = end_line.min(lines.len().saturating_sub(1));
    let snippet = if start_line <= end_line_capped && start_line < lines.len() {
        lines[start_line..=end_line_capped].join("\n")
    } else {
        String::new()
    };

    let success_msg = format!(
        "The file {} has been edited. Here's a snippet (starting at line {}):\n{}\n\nReview the changes and make sure they are as expected.",
        path,
        start_line + 1,
        snippet
    );

    Ok(ToolExecResult {
        output: Some(success_msg),
        error: None,
        error_code: None,
    })
}

fn expand_tabs_fixed(s: &str, tabsize: usize) -> String {
    let mut out = String::with_capacity(s.len());
    let mut col = 0usize;
    for ch in s.chars() {
        match ch {
            '\t' => {
                let spaces = tabsize - (col % tabsize);
                for _ in 0..spaces {
                    out.push(' ');
                }
                col += spaces;
            }
            '\n' => {
                out.push('\n');
                col = 0;
            }
            _ => {
                out.push(ch);
                col += 1;
            }
        }
    }
    out
}

async fn insert_handler(
    path: &str,
    args: &HashMap<String, serde_json::Value>,
) -> Result<ToolExecResult, EditFileError> {
    let insert_line_val = args.get("insert_line");
    let insert_line = match insert_line_val.and_then(|v| v.as_i64()) {
        Some(v) if v >= 0 => v as usize,
        _ => {
            return Ok(ToolExecResult {
                output: None,
                error: Some(
                    "Parameter `insert_line` is required and should be integer for command: insert"
                        .to_string(),
                ),
                error_code: Some(-1),
            });
        }
    };

    let new_str_val = args.get("new_str");
    let new_str = match new_str_val.and_then(|v| v.as_str()) {
        Some(s) => s,
        None => {
            return Ok(ToolExecResult {
                output: None,
                error: Some("Parameter `new_str` is required for command: insert".to_string()),
                error_code: Some(-1),
            });
        }
    };

    let file_text_raw = fs::read_to_string(path).map_err(|_| EditFileError::Io)?;
    let file_text = expand_tabs_fixed(&file_text_raw, TAB_WIDTH);
    let new_str_expanded = expand_tabs_fixed(new_str, TAB_WIDTH);
    let file_text_lines: Vec<&str> = file_text.split('\n').collect();
    let n_lines_file = file_text_lines.len();

    if insert_line > n_lines_file {
        let msg = format!(
            "Invalid `insert_line` parameter: {}. It should be within the range of lines of the file: [0, {}]",
            insert_line, n_lines_file
        );
        return Ok(ToolExecResult {
            output: None,
            error: Some(msg),
            error_code: Some(-1),
        });
    }

    let new_str_lines: Vec<&str> = new_str_expanded.split('\n').collect();
    let mut new_file_text_lines: Vec<String> =
        Vec::with_capacity(file_text_lines.len() + new_str_lines.len());

    for &l in &file_text_lines[..insert_line] {
        new_file_text_lines.push(l.to_string());
    }
    for &l in &new_str_lines {
        new_file_text_lines.push(l.to_string());
    }
    for &l in &file_text_lines[insert_line..] {
        new_file_text_lines.push(l.to_string());
    }

    let snippet_start = insert_line.saturating_sub(SNIPPET_LINES);
    let snippet_end = (insert_line + SNIPPET_LINES).min(file_text_lines.len());
    let mut snippet_lines: Vec<String> = Vec::new();

    for &l in &file_text_lines[snippet_start..insert_line] {
        snippet_lines.push(l.to_string());
    }
    for &l in &new_str_lines {
        snippet_lines.push(l.to_string());
    }
    for &l in &file_text_lines[insert_line..snippet_end] {
        snippet_lines.push(l.to_string());
    }

    let new_file_text = new_file_text_lines.join("\n");
    let snippet = snippet_lines.join("\n");

    fs::write(path, new_file_text).map_err(|_| EditFileError::Io)?;

    let success_msg = format!(
        "The file {} has been edited. Here's a snippet of the edited file (starting at line {}):\n{}\n\nReview the changes and make sure they are as expected.",
        path,
        std::cmp::max(1, insert_line.saturating_sub(SNIPPET_LINES) + 1),
        snippet
    );

    Ok(ToolExecResult {
        output: Some(success_msg),
        error: None,
        error_code: None,
    })
}

async fn create_handler(
    path: &str,
    args: &HashMap<String, serde_json::Value>,
) -> Result<ToolExecResult, EditFileError> {
    let new_str = args
        .get("new_str")
        .and_then(|v| v.as_str())
        .ok_or(EditFileError::NewStringError)?;

    // Check if file already exists
    if std::path::Path::new(path).exists() {
        return Err(EditFileError::Other(format!(
            "File already exists: {}. Use replace or insert commands to modify existing files.",
            path
        )));
    }

    // Create parent directories if they don't exist
    if let Some(parent) = std::path::Path::new(path).parent()
        && let Err(e) = std::fs::create_dir_all(parent)
    {
        return Err(EditFileError::Other(format!(
            "Failed to create parent directories for {}: {}",
            path, e
        )));
    }

    // Write the new content to the file
    if let Err(e) = fs::write(path, new_str) {
        return Err(EditFileError::Other(format!(
            "Failed to create file {}: {}",
            path, e
        )));
    }

    let lines_count = new_str.lines().count();
    let success_msg = format!(
        "File created successfully at {} with {} lines",
        path, lines_count
    );

    Ok(ToolExecResult {
        output: Some(success_msg),
        error: None,
        error_code: None,
    })
}

#[derive(Error, Debug)]
enum EditFileError {
    #[error("Parameter 'new_str' is required for replace command")]
    NewStringError,

    #[error("Parameter 'old_str' cannot be empty")]
    EmptyOldString,

    #[error("IO error occurred")]
    Io,

    #[error("Old string not found in file `{0}`")]
    OldStringNotExists(String),

    #[error("Multiple occurrences of old string found, first at line {0}")]
    MultipleOccurrences(u64),

    #[error("Other error: {0}")]
    Other(String),
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::{NamedTempFile, TempDir};

    #[tokio::test]
    async fn test_create_handler_missing_new_str() {
        let temp_dir = TempDir::new().unwrap();
        let temp_path = temp_dir.path().join("test_file.txt");
        let path = temp_path.to_str().unwrap();

        let mut args = HashMap::new();
        args.insert(
            "path".to_string(),
            serde_json::Value::String(path.to_string()),
        );
        args.insert(
            "command".to_string(),
            serde_json::Value::String("create".to_string()),
        );

        let mut edit_file = EditFile::default();
        let result = edit_file.execute(args).await;
        assert!(result.is_err());

        // Verify no file was created
        assert!(!temp_path.exists());
    }

    #[tokio::test]
    async fn test_create_new_file() {
        let temp_dir = TempDir::new().unwrap();
        let temp_path = temp_dir.path().join("test_file.txt");
        let path = temp_path.to_str().unwrap();

        let mut args = HashMap::new();
        args.insert(
            "path".to_string(),
            serde_json::Value::String(path.to_string()),
        );
        args.insert(
            "command".to_string(),
            serde_json::Value::String("create".to_string()),
        );
        args.insert(
            "new_str".to_string(),
            serde_json::Value::String("Hello, world!".to_string()),
        );

        let mut edit_file = EditFile::default();
        let result = edit_file.execute(args).await;
        assert!(result.is_ok());

        // Verify file was created with correct content
        assert!(temp_path.exists());
        let content = fs::read_to_string(&temp_path).unwrap();
        assert_eq!(content, "Hello, world!");

        // File cleanup is automatic when temp_dir is dropped
    }

    #[tokio::test]
    async fn test_create_file_already_exists() {
        let temp_file = NamedTempFile::new().unwrap();
        let path = temp_file.path().to_str().unwrap();

        let mut args = HashMap::new();
        args.insert(
            "path".to_string(),
            serde_json::Value::String(path.to_string()),
        );
        args.insert(
            "command".to_string(),
            serde_json::Value::String("create".to_string()),
        );
        args.insert(
            "new_str".to_string(),
            serde_json::Value::String("Hello, world!".to_string()),
        );

        let mut edit_file = EditFile::default();
        let result = edit_file.execute(args).await;
        assert!(result.is_err());

        if let Err(msg) = result {
            assert!(msg.contains("File already exists"));
        } else {
            panic!("Expected error message containing 'File already exists'");
        }
    }

    #[tokio::test]
    async fn test_replace_handler() {
        let temp_file = NamedTempFile::new().unwrap();
        let path = temp_file.path().to_str().unwrap();

        // Write initial content
        fs::write(path, "Hello, world!\nThis is a test file.").unwrap();

        let mut args = HashMap::new();
        args.insert(
            "path".to_string(),
            serde_json::Value::String(path.to_string()),
        );
        args.insert(
            "command".to_string(),
            serde_json::Value::String("replace".to_string()),
        );
        args.insert(
            "old_str".to_string(),
            serde_json::Value::String("world".to_string()),
        );
        args.insert(
            "new_str".to_string(),
            serde_json::Value::String("Rust".to_string()),
        );

        let mut edit_file = EditFile::default();
        let result = edit_file.execute(args).await;
        assert!(result.is_ok());

        // Verify content was replaced
        let content = fs::read_to_string(path).unwrap();
        assert_eq!(content, "Hello, Rust!\nThis is a test file.");
    }

    #[tokio::test]
    async fn test_replace_handler_old_str_not_found() {
        let temp_file = NamedTempFile::new().unwrap();
        let path = temp_file.path().to_str().unwrap();

        // Write initial content
        fs::write(path, "Hello, world!\nThis is a test file.").unwrap();

        let mut args = HashMap::new();
        args.insert(
            "path".to_string(),
            serde_json::Value::String(path.to_string()),
        );
        args.insert(
            "command".to_string(),
            serde_json::Value::String("replace".to_string()),
        );
        args.insert(
            "old_str".to_string(),
            serde_json::Value::String("nonexistent".to_string()),
        );
        args.insert(
            "new_str".to_string(),
            serde_json::Value::String("replacement".to_string()),
        );

        let mut edit_file = EditFile::default();
        let result = edit_file.execute(args).await;
        assert!(result.is_err());

        if let Err(msg) = result {
            assert!(msg.contains("Old string not found"));
        } else {
            panic!("Expected error message containing 'Old string not found'");
        }
    }

    #[tokio::test]
    async fn test_replace_handler_multiple_occurrences() {
        let temp_file = NamedTempFile::new().unwrap();
        let path = temp_file.path().to_str().unwrap();

        // Write initial content with multiple occurrences
        fs::write(path, "test test test").unwrap();

        let mut args = HashMap::new();
        args.insert(
            "path".to_string(),
            serde_json::Value::String(path.to_string()),
        );
        args.insert(
            "command".to_string(),
            serde_json::Value::String("replace".to_string()),
        );
        args.insert(
            "old_str".to_string(),
            serde_json::Value::String("test".to_string()),
        );
        args.insert(
            "new_str".to_string(),
            serde_json::Value::String("replacement".to_string()),
        );

        let mut edit_file = EditFile::default();
        let result = edit_file.execute(args).await;
        assert!(result.is_err());

        if let Err(msg) = result {
            assert!(msg.contains("Multiple occurrences"));
        } else {
            panic!("Expected error message containing 'Multiple occurrences'");
        }
    }

    #[tokio::test]
    async fn test_insert_handler() {
        let temp_file = NamedTempFile::new().unwrap();
        let path = temp_file.path().to_str().unwrap();

        // Write initial content
        fs::write(path, "Line 1\nLine 2\nLine 3").unwrap();

        let mut args = HashMap::new();
        args.insert(
            "path".to_string(),
            serde_json::Value::String(path.to_string()),
        );
        args.insert(
            "command".to_string(),
            serde_json::Value::String("insert".to_string()),
        );
        args.insert(
            "insert_line".to_string(),
            serde_json::Value::Number(serde_json::Number::from(2)),
        );
        args.insert(
            "new_str".to_string(),
            serde_json::Value::String("Inserted Line".to_string()),
        );

        let mut edit_file = EditFile::default();
        let result = edit_file.execute(args).await;
        assert!(result.is_ok());

        // Verify content was inserted
        let content = fs::read_to_string(path).unwrap();
        assert_eq!(content, "Line 1\nLine 2\nInserted Line\nLine 3");
    }

    #[tokio::test]
    async fn test_insert_handler_invalid_line() {
        let temp_file = NamedTempFile::new().unwrap();
        let path = temp_file.path().to_str().unwrap();

        // Write initial content
        fs::write(path, "Line 1\nLine 2").unwrap();

        let mut args = HashMap::new();
        args.insert(
            "path".to_string(),
            serde_json::Value::String(path.to_string()),
        );
        args.insert(
            "command".to_string(),
            serde_json::Value::String("insert".to_string()),
        );
        args.insert(
            "insert_line".to_string(),
            serde_json::Value::Number(serde_json::Number::from(10)),
        );
        args.insert(
            "new_str".to_string(),
            serde_json::Value::String("Inserted Line".to_string()),
        );

        let mut edit_file = EditFile::default();
        let result = edit_file.execute(args).await;
        assert!(result.is_err());

        // Check that it returns an error message
        if let Err(msg) = result {
            assert!(msg.contains("Invalid `insert_line` parameter"));
        } else {
            panic!("Expected error message containing 'Invalid `insert_line` parameter'");
        }
    }
}
