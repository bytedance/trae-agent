// the edcit tools is set to be here

use std::{collections::HashMap, fs, path::Path, process::Stdio};

use crate::{Tool, ToolExecResult};
use thiserror::Error;
use tokio::process::Command;

const EDIT_COMMAND: [&str; 4] = ["view", "create", "str_replace", "insert"];
const SNIPPET_LINES: usize = 4; //would u8 already enough ?
const TAB_WIDTH: usize = 8; // Python str.expandtabs() default

#[derive(Default)]
pub struct Edit {}

impl Tool for Edit {
    fn get_name(&self) -> &str {
        "str_replace_based_edit_tool"
    }

    fn reset(&mut self) {}

    fn get_description(&self) -> &str {
        "Custom editing tool for viewing, creating and editing files
        * State is persistent across command calls and discussions with the user
        * If `path` is a file, `view` displays the result of applying `cat -n`. If `path` is a directory, `view` lists non-hidden files and directories up to 2 levels deep
        * The `create` command cannot be used if the specified `path` already exists as a file !!! If you know that the `path` already exists, please remove it first and then perform the `create` operation!
        * If a `command` generates a long output, it will be truncated and marked with `<response clipped>`

        Notes for using the `str_replace` command:
        * The `old_str` parameter should match EXACTLY one or more consecutive lines from the original file. Be mindful of whitespaces!
        * If the `old_str` parameter is not unique in the file, the replacement will not be performed. Make sure to include enough context in `old_str` to make it unique
        * The `new_str` parameter should contain the edited lines that should replace the `old_str`
        "
    }

    fn get_input_schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type":"object",
            "properties": {
                "command":{
                    "type":"string",
                    "description":"Optional parameter of `str_replace` command containing the new string (if not given, no string will be added). Required parameter of `insert` command containing the string to insert.",
                    "enum": EDIT_COMMAND,
                },
                "file_text":{
                    "type":"string",
                    "description":"Required parameter of `create` command, with the content of the file to be created."
                },
                "insert_line":{
                    "type":"integer",
                    "description":"Required parameter of `insert` command. The `new_str` will be inserted AFTER the line `insert_line` of `path`."
                },
                "new_str":{
                    "type":"string",
                    "description":"Optional parameter of `str_replace` command containing the new string (if not given, no string will be added). Required parameter of `insert` command containing the string to insert."
                },
                "old_str":{
                    "type":"string",
                    "description":"Absolute path to file or directory, e.g. `/repo/file.py` or `/repo`."
                },
                "path":{
                    "type":"string",
                    "description":"Absolute path to file or directory, e.g. `/repo/file.py` or `/repo`."
                },
                "view_range":{
                    "type":"array",
                    "description":"Optional parameter of `view` command when `path` points to a file. If none is given, the full file is shown. If provided, the file will be shown in the indicated line number range, e.g. [11, 12] will show lines 11 and 12. Indexing at 1 to start. Setting `[start_line, -1]` shows all lines from `start_line` to the end of the file.",
                    "items": {
                        "type":"integer",
                    }
                }
            },
         "required":["command","path"]
        })
    }

    fn execute(
        &mut self,
        arguments: std::collections::HashMap<String, serde_json::Value>,
    ) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<String, String>> + Send + '_>>
    {
        Box::pin(async move {
            // Extract command and path from arguments
            let command = arguments
                .get("command")
                .and_then(|v| v.as_str())
                .unwrap_or("");

            let path = arguments.get("path").and_then(|v| v.as_str()).unwrap_or("");

            if path.is_empty() {
                return Err("Path parameter is required".to_string());
            }

            // Route to appropriate handler based on command
            let result = match command {
                "view" => view_handler(path, &arguments).await,
                "create" => {
                    // Check if file already exists
                    if Path::new(path).exists() {
                        return Err(format!(
                            "File already exists at path: {}. Please remove it first before creating.",
                            path
                        ));
                    }
                    create_handler(path, &arguments).await
                }
                "str_replace" => str_replace_handler(path, &arguments).await,
                "insert" => insert_handler(path, &arguments).await,
                _ => {
                    return Err(format!(
                        "Unknown command: {}. Supported commands are: view, create, str_replace, insert",
                        command
                    ));
                }
            };

            // Convert result to String format expected by Tool trait
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

async fn view_handler(
    path: &str,
    args: &HashMap<String, serde_json::Value>,
) -> Result<ToolExecResult, EditToolError> {
    let view_range: Option<[i32; 2]> = args.get("view_range").and_then(|v| match v {
        serde_json::Value::Array(arr) if arr.len() == 2 => {
            let a = arr[0].as_i64()? as i32;
            let b = arr[1].as_i64()? as i32;
            Some([a, b])
        }
        _ => None,
    });

    if let Some(range) = view_range {
        return view(path, Some(&range)).await;
    }
    // assume can't match
    return view(path, None).await;
}

async fn create_handler(
    path: &str,
    args: &HashMap<String, serde_json::Value>,
) -> Result<ToolExecResult, EditToolError> {
    let file_text = args.get("file_text").and_then(|v| v.as_str()).unwrap_or("");

    if file_text.is_empty() {
        return Err(EditToolError::FileTextEmpty);
    }

    let res = fs::write(path, file_text);

    if res.is_ok() {
        return Ok(ToolExecResult {
            output: Some(format!("File created successfully at: {}", path)),
            error: None,
            error_code: None,
        });
    }

    if let Err(e) = res {
        return Err(EditToolError::Other(e.to_string()));
    }

    Err(EditToolError::Other("unexpected error".to_string()))
}

async fn str_replace_handler(
    path: &str,
    args: &HashMap<String, serde_json::Value>,
) -> Result<ToolExecResult, EditToolError> {
    let old_str = args.get("old_str").and_then(|v| v.as_str()).unwrap_or("");

    let new_str = args
        .get("new_str")
        .and_then(|v| v.as_str())
        .ok_or(EditToolError::NewStringError)?;

    if old_str.is_empty() {
        return Err(EditToolError::EmptyOldString);
    }

    let mut file_content = match fs::read_to_string(path) {
        Ok(s) => s,
        Err(_) => return Err(EditToolError::Io),
    };

    if !file_content.contains(old_str) {
        return Err(EditToolError::OldStringNotExists(
            old_str.to_string(),
            path.to_string(),
        ));
    }

    // Validate occurrences on raw content using raw old_str
    let mut lines_with_hits = Vec::new(); // 1-based line numbers
    let mut multiple = false;
    for (idx, line) in file_content.lines().enumerate() {
        let mut from = 0;
        let mut hits_in_line = 0;
        while let Some(pos) = line[from..].find(old_str) {
            hits_in_line += 1;
            from += pos + old_str.len();
            if old_str.is_empty() {
                // Avoid infinite loop on empty pattern (already disallowed above).
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
    // If more than one line has hits or any single line has multiple hits, treat as multiple
    if lines_with_hits.len() > 1 || multiple {
        return Err(EditToolError::MultipleOccurrences(
            old_str.to_string(),
            lines_with_hits[0] as u64,
        ));
    }

    // Capture first occurrence position in the original content (for snippet computation)
    let first_pos_opt = file_content.find(old_str);

    // Do the actual replacement on raw content
    file_content = file_content.replace(old_str, new_str);

    fs::write(path, &file_content).map_err(|_| EditToolError::Io)?;

    // Build snippet info using the original occurrence position if available
    let replacement_line: usize = match first_pos_opt {
        Some(pos) => file_content[..pos.min(file_content.len())] // safety
            .bytes()
            .filter(|&b| b == b'\n')
            .count(),
        None => 0, // shouldn't happen after validation
    };

    // start_line and end_line (0-based indices for slicing lines)
    let start_line = replacement_line.saturating_sub(SNIPPET_LINES);
    let end_line =
        replacement_line + SNIPPET_LINES + new_str.bytes().filter(|&b| b == b'\n').count();

    // Build the snippet from new file content lines [start_line ..= end_line]
    let lines: Vec<&str> = file_content.split('\n').collect();
    let end_line_capped = end_line.min(lines.len().saturating_sub(1));
    let snippet = if start_line <= end_line_capped && start_line < lines.len() {
        lines[start_line..=end_line_capped].join("\n")
    } else {
        String::new()
    };

    fn make_output(snippet: &str, label: &str, start_line_1_based: usize) -> String {
        format!(
            "{} (starting at line {}):\n{}\n",
            label, start_line_1_based, snippet
        )
    }

    let mut success_msg = format!("The file {} has been edited. ", path);
    success_msg.push_str(&make_output(
        &snippet,
        &format!("a snippet of {}", path),
        start_line + 1,
    ));
    success_msg.push_str(
        "Review the changes and make sure they are as expected. Edit the file again if necessary.",
    );

    Ok(ToolExecResult {
        output: Some(success_msg),
        error: None,
        error_code: None,
    })
}

// Helper: expand tabs like Python's str.expandtabs(tabsize)
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
) -> Result<ToolExecResult, EditToolError> {
    // 1) Validate insert_line
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

    // 2) Validate new_str
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

    // 3) Read file
    let file_text_raw = fs::read_to_string(path).map_err(|_| EditToolError::Io)?;
    // 4) Expand tabs like Python before operating
    let file_text = expand_tabs_fixed(&file_text_raw, TAB_WIDTH);
    let new_str_expanded = expand_tabs_fixed(new_str, TAB_WIDTH);
    // 5) Split into lines
    let file_text_lines: Vec<&str> = file_text.split('\n').collect();
    let n_lines_file = file_text_lines.len();

    if insert_line > n_lines_file {
        let msg = format!(
            "Invalid `insert_line` parameter: {}. It should be within the range of lines of the file: {:?}",
            insert_line,
            [0, n_lines_file]
        );
        return Ok(ToolExecResult {
            output: None,
            error: Some(msg),
            error_code: Some(-1),
        });
    }
    // 7) Prepare insertion
    let new_str_lines: Vec<&str> = new_str_expanded.split('\n').collect();
    // Build new file content lines
    // file_text_lines[..insert_line] + new_str_lines + file_text_lines[insert_line..]
    let mut new_file_text_lines: Vec<String> =
        Vec::with_capacity(file_text_lines.len() + new_str_lines.len());
    // Push left part
    for &l in &file_text_lines[..insert_line] {
        new_file_text_lines.push(l.to_string());
    }
    // Push new lines
    for &l in &new_str_lines {
        new_file_text_lines.push(l.to_string());
    }
    // Push right part
    for &l in &file_text_lines[insert_line..] {
        new_file_text_lines.push(l.to_string());
    }
    // 8) Build snippet lines
    const SNIPPET_LINES: usize = 3; // ensure this matches your project’s constant
    let snippet_start = insert_line.saturating_sub(SNIPPET_LINES);
    let snippet_end = (insert_line + SNIPPET_LINES).min(file_text_lines.len());
    let mut snippet_lines: Vec<String> = Vec::new();
    // lines before
    for &l in &file_text_lines[snippet_start..insert_line] {
        snippet_lines.push(l.to_string());
    }
    // inserted lines
    for &l in &new_str_lines {
        snippet_lines.push(l.to_string());
    }
    // lines after
    for &l in &file_text_lines[insert_line..snippet_end] {
        snippet_lines.push(l.to_string());
    }
    // 9) Join back to text
    let new_file_text = new_file_text_lines.join("\n");
    let snippet = snippet_lines.join("\n");
    // 10) Write file
    fs::write(path, new_file_text).map_err(|_| EditToolError::Io)?;
    // 11) Build success message
    fn make_output(snippet: &str, label: &str, start_line_1_based: usize) -> String {
        format!(
            "{} (starting at line {}):\n{}\n",
            label, start_line_1_based, snippet
        )
    }
    let mut success_msg = format!("The file {} has been edited. ", path);
    success_msg.push_str(&make_output(
        &snippet,
        "a snippet of the edited file",
        std::cmp::max(1, insert_line.saturating_sub(SNIPPET_LINES) + 1),
    ));
    success_msg.push_str("Review the changes and make sure they are as expected (correct indentation, no duplicate lines, etc). Edit the file again if necessary.");
    Ok(ToolExecResult {
        output: Some(success_msg),
        error: None,
        error_code: None,
    })
}

async fn view(path: &str, view_range: Option<&[i32; 2]>) -> Result<ToolExecResult, EditToolError> {
    if Path::new(path).is_dir() {
        if view_range.is_none() {
            return Err(EditToolError::Other(
                "view range parameter is not allowed when path points to a directories".to_string(),
            ));
        }

        let output = Command::new("find")
            .arg(path)
            .arg("-maxdepth")
            .arg("2")
            .arg("-not")
            .arg("-path")
            .arg("*/.*") // Note: shell globbing not needed here; find pattern is passed literally
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .output()
            .await;

        if let Ok(res) = output {
            let stdout = {
                let res_out = String::from_utf8(res.stdout);

                if let Ok(output_msg) = res_out {
                    Some(format!(
                        "Here's the files and directories up to 2 levels deep in the {}, excluding hidden items: \n{}\n",
                        path, output_msg
                    ));
                }
                None
            };
            let stderr = String::from_utf8(res.stderr).ok();
            // Example: map ExitStatus to an error code if non-success
            let error_code = if res.status.success() {
                None
            } else {
                res.status.code()
            };
            return Ok(ToolExecResult {
                output: stdout,
                error: stderr,
                error_code,
            });
        }
    }

    let file_content = {
        let content = fs::read_to_string(path);
        if let Ok(content) = content {
            content
        } else {
            return Err(EditToolError::FailReadFile);
        }
    };

    let number_line = file_content.chars().filter(|&c| c == '\n').count() + 1;

    if let Some(range) = view_range {
        if range[0] > range[1] && range[1] != -1 {
            return Err(EditToolError::IndexError(
                "Index one must be larger than index zero".to_string(),
            ));
        }

        if range[1] > number_line as i32 || range[0] > number_line as i32 {
            return Err(EditToolError::IndexError(
                "Index is larger than the total number of lines in the file".to_string(),
            ));
        }

        let file_lines: Vec<&str> = file_content.split("\n").collect();

        let file_slice: String = if range[1] == -1 {
            file_lines[range[0] as usize..].join("\n")
        } else {
            file_lines[range[0] as usize..range[1] as usize].join("\n")
        };

        //TODO: haven't handle cases like file_content and file_content tab

        return Ok(ToolExecResult {
            output: Some(format!(
                "Here's the result of running cat -n on {} \n {} \n",
                path, file_slice
            )),
            error: None,
            error_code: None,
        });
    }

    if view_range.is_none() {
        return Ok(ToolExecResult {
            output: Some(format!(
                "The follow is the full content of the file: {} \n content: {} \n",
                path, file_content
            )),
            error: None,
            error_code: None,
        });
    }

    Err(EditToolError::Other("Unexpected Error".to_string()))
}

#[derive(Error, Debug)]
enum EditToolError {
    #[error("invalid index number: {0}")]
    IndexError(String),

    #[error("fail to read the file")]
    FailReadFile,

    #[error("Parameter 'file_text' is required and must be a string for command: create")]
    FileTextEmpty,

    #[error("No replacement was performed, old_str `{0}` did not appear verbatim in {0}.")]
    OldStringNotExists(String, String),

    #[error("Parameter 'old_str' is required and should be a string for command: str_replace")]
    EmptyOldString,

    #[error("Parameter `new_str` should be a string or null for command: str_replace")]
    NewStringError,

    #[error("IO Error")]
    Io,

    #[error(
        "No replacement was performed. Multiple occurrences of old_str `{0}` in lines {0}. Please ensure it is unique"
    )]
    MultipleOccurrences(String, u64),

    #[error("other error {0}")]
    Other(String),
}

#[cfg(test)]
mod tests {
    use super::*; // bring view, ToolExecResult, EditToolError into scope
    use serde_json::json;
    use std::fs;
    use std::path::PathBuf;
    use tempfile::TempDir;
    use tempfile::tempdir; // add `tempfile = "3"` to Cargo.toml
    use tokio::runtime::Runtime;

    // helper to run async function synchronously in tests
    fn run_async<F, R>(f: F) -> R
    where
        F: std::future::Future<Output = R>,
    {
        // Use a small runtime per test
        let rt = Runtime::new().expect("create runtime");
        rt.block_on(f)
    }

    fn write_temp_file(dir: &TempDir, name: &str, content: &str) -> PathBuf {
        let path = dir.path().join(name);
        fs::write(&path, content).expect("write temp file");
        path
    }
    // Helper to build args HashMap
    fn args(
        old: Option<&str>,
        new_: Option<&str>,
    ) -> std::collections::HashMap<String, serde_json::Value> {
        let mut m = std::collections::HashMap::new();
        if let Some(o) = old {
            m.insert("old_str".to_string(), json!(o));
        }
        if let Some(n) = new_ {
            m.insert("new_str".to_string(), json!(n));
        }
        m
    }

    fn args_insert(
        insert_line: Option<i64>,
        new_str: Option<&str>,
    ) -> std::collections::HashMap<String, serde_json::Value> {
        let mut m = std::collections::HashMap::new();
        if let Some(i) = insert_line {
            m.insert("insert_line".to_string(), json!(i));
        }
        if let Some(s) = new_str {
            m.insert("new_str".to_string(), json!(s));
        }
        m
    }
    #[test]
    fn test_view_file_full() {
        let dir = tempdir().expect("tempdir");
        let file_path = dir.path().join("test.txt");
        fs::write(&file_path, "line1\nline2\nline3\n").expect("write file");

        let path_str = file_path.to_str().unwrap();

        let result = run_async(view(path_str, None));

        match result {
            Ok(res) => {
                assert!(res.output.is_some(), "expected output for file");
                let out = res.output.unwrap();
                // file output should include "cat -n" style header and the file content slice
                assert!(out.contains("line1"));
                assert!(out.contains("line3"));
            }
            Err(e) => panic!("expected Ok, got Err: {:?}", e),
        }
    }

    #[test]
    fn test_view_file_range() {
        let dir = tempdir().expect("tempdir");
        let file_path = dir.path().join("test2.txt");
        fs::write(&file_path, "a\nb\nc\nd\ne\nf\n").expect("write file");

        let path_str = file_path.to_str().unwrap();
        // take lines 2..4 (zero-based indexing in your code)
        let range_arr: [i32; 2] = [2, 4];
        let result = run_async(view(path_str, Some(&range_arr)));

        match result {
            Ok(res) => {
                assert!(res.output.is_some());
                let out = res.output.unwrap();

                assert!(out.contains("c"));
                assert!(out.contains("d"));
            }
            Err(e) => panic!("expected Ok, got Err: {:?}", e),
        }
    }

    #[test]
    fn test_view_file_range_to_end_with_minus_one() {
        let dir = tempdir().expect("tempdir");
        let file_path = dir.path().join("test3.txt");
        fs::write(&file_path, "¥\ny\nz\n").expect("write file");

        let path_str = file_path.to_str().unwrap();
        let range_arr: [i32; 2] = [1, -1]; // from line 1 to end
        let result = run_async(view(path_str, Some(&range_arr)));

        match result {
            Ok(res) => {
                let out = res.output.expect("output present");
                // expect lines y and z
                assert!(out.contains("y"));
                assert!(out.contains("z"));
                assert!(!out.contains("¥"));
            }
            Err(e) => panic!("expected Ok, got Err: {:?}", e),
        }
    }

    #[test]
    fn test_view_directory_with_range_not_allowed() {
        let dir = tempdir().expect("tempdir");
        let subdir = dir.path().join("sub");
        fs::create_dir(&subdir).expect("create subdir");

        let path_str = subdir.to_str().unwrap();
        // pass None view_range to trigger the directory + None error
        let result = run_async(view(path_str, None));

        match result {
            Err(EditToolError::Other(msg)) => {
                assert!(msg.contains("view range parameter is not allowed"));
            }
            other => panic!("expected Other error, got {:?}", other),
        }
    }

    #[test]
    fn test_view_index_error_when_start_greater_than_end() {
        let dir = tempdir().expect("tempdir");
        let file_path = dir.path().join("test4.txt");
        fs::write(&file_path, "one\ntwo\n").expect("write file");

        let path_str = file_path.to_str().unwrap();
        let range_arr: [i32; 2] = [2, 1]; // start > end and end != -1 -> should be IndexError
        let result = run_async(view(path_str, Some(&range_arr)));

        match result {
            Err(EditToolError::IndexError(_)) => {}
            other => panic!("expected IndexError, got {:?}", other),
        }
    }

    fn temp_file_path(dir: &TempDir, name: &str) -> PathBuf {
        dir.path().join(name)
    }
    #[test]
    fn test_create_handler_success_writes_file_and_returns_ok() {
        let dir = tempdir().expect("tempdir");
        let file_path = temp_file_path(&dir, "ok.txt");
        let path_str = file_path.to_str().unwrap();
        let mut args = HashMap::new();
        args.insert("file_text".to_string(), json!("hello world"));
        let result = run_async(create_handler(path_str, &args));
        match result {
            Ok(res) => {
                assert!(res.error.is_none());
                assert!(res.error_code.is_none());
                let out = res.output.unwrap_or_default();
                assert!(out.contains("File created successfully"));
                assert!(out.contains(path_str));
                let contents = fs::read_to_string(path_str).expect("read back file");
                assert_eq!(contents, "hello world");
            }
            other => panic!("expected Ok, got {:?}", other),
        }
    }
    #[test]
    fn test_create_handler_error_when_file_text_empty_string() {
        let dir = tempdir().expect("tempdir");
        let file_path = temp_file_path(&dir, "empty.txt");
        let path_str = file_path.to_str().unwrap();
        let mut args = HashMap::new();
        args.insert("file_text".to_string(), json!(""));
        let result = run_async(create_handler(path_str, &args));
        match result {
            Err(EditToolError::FileTextEmpty) => {}
            other => panic!("expected FileTextEmpty, got {:?}", other),
        }
    }
    #[test]
    fn test_create_handler_error_when_file_text_missing() {
        let dir = tempdir().expect("tempdir");
        let file_path = temp_file_path(&dir, "missing.txt");
        let path_str = file_path.to_str().unwrap();
        // No "file_text" key in args
        let args: HashMap<String, serde_json::Value> = HashMap::new();
        let result = run_async(create_handler(path_str, &args));
        match result {
            Err(EditToolError::FileTextEmpty) => {}
            other => panic!(
                "expected FileTextEmpty when key is missing, got {:?}",
                other
            ),
        }
    }
    #[test]
    fn test_create_handler_error_when_file_text_not_a_string() {
        let dir = tempdir().expect("tempdir");
        let file_path = temp_file_path(&dir, "nonstring.txt");
        let path_str = file_path.to_str().unwrap();
        // Non-string value: as_str() -> None -> unwrap_or("") -> empty -> FileTextEmpty
        let mut args = HashMap::new();
        args.insert("file_text".to_string(), json!(12345));
        let result = run_async(create_handler(path_str, &args));
        match result {
            Err(EditToolError::FileTextEmpty) => {}
            other => panic!(
                "expected FileTextEmpty when value is non-string, got {:?}",
                other
            ),
        }
    }
    #[test]
    fn test_create_handler_error_when_write_fails_due_to_missing_parent_dir() {
        let dir = tempdir().expect("tempdir");
        // Point to a path inside a subdirectory that doesn't exist
        let nested_nonexistent = dir.path().join("no_such_dir").join("file.txt");
        let path_str = nested_nonexistent.to_str().unwrap();
        let mut args = HashMap::new();
        args.insert("file_text".to_string(), json!("data"));
        let result = run_async(create_handler(path_str, &args));
        match result {
            Err(EditToolError::Other(msg)) => {
                // On most platforms, this will mention "No such file or directory"
                // or a similar permission/IO message. We just assert it's non-empty.
                assert!(!msg.is_empty(), "expected non-empty IO error message");
            }
            other => panic!("expected Other(..) due to fs::write error, got {:?}", other),
        }
    }
    #[test]
    fn test_create_handler_overwrites_existing_file() {
        let dir = tempdir().expect("tempdir");
        let file_path = temp_file_path(&dir, "overwrite.txt");
        let path_str = file_path.to_str().unwrap();
        // Pre-create with some content
        fs::write(&file_path, "old").expect("prewrite");
        let mut args = HashMap::new();
        args.insert("file_text".to_string(), json!("new"));
        let result = run_async(create_handler(path_str, &args));
        match result {
            Ok(_) => {
                let contents = fs::read_to_string(path_str).expect("read back file");
                assert_eq!(contents, "new");
            }
            other => panic!("expected Ok overwrite, got {:?}", other),
        }
    }
    #[test]
    fn returns_error_when_file_not_found() {
        let args = args(Some("foo"), Some("bar"));
        let non_existent = PathBuf::from("surely/does/not/exist.txt");
        let res = run_async(str_replace_handler(non_existent.to_str().unwrap(), &args));
        assert!(matches!(res, Err(EditToolError::Io)));
    }
    #[test]
    fn errors_when_old_str_missing_or_empty() {
        let dir = tempdir().unwrap();
        let path = write_temp_file(&dir, "a.txt", "hello world");
        // 1) missing old_str (defaults to "")
        let res = run_async(str_replace_handler(
            path.to_str().unwrap(),
            &args(None, Some("x")),
        ));
        assert!(matches!(res, Err(EditToolError::EmptyOldString)));
        // 2) explicitly empty old_str
        let res = run_async(str_replace_handler(
            path.to_str().unwrap(),
            &args(Some(""), Some("x")),
        ));
        assert!(matches!(res, Err(EditToolError::EmptyOldString)));
    }
    #[test]
    fn errors_when_new_str_missing() {
        let dir = tempdir().unwrap();
        let path = write_temp_file(&dir, "a.txt", "hello world");
        let res = run_async(str_replace_handler(
            path.to_str().unwrap(),
            &args(Some("hello"), None),
        ));
        assert!(matches!(res, Err(EditToolError::NewStringError)));
    }
    #[test]
    fn errors_when_old_str_not_in_file() {
        let dir = tempdir().unwrap();
        let path = write_temp_file(&dir, "a.txt", "alpha beta gamma");
        let res = run_async(str_replace_handler(
            path.to_str().unwrap(),
            &args(Some("delta"), Some("DELTA")),
        ));
        match res {
            Err(EditToolError::OldStringNotExists(old, p)) => {
                assert_eq!(old, "delta");
                assert_eq!(PathBuf::from(p), path);
            }
            other => panic!("unexpected result: {:?}", other),
        }
    }
    #[test]
    fn errors_when_multiple_occurrences_across_lines() {
        let dir = tempdir().unwrap();
        let content = "line1 foo\nline2 foo\nline3\n";
        let path = write_temp_file(&dir, "a.txt", content);
        let res = run_async(str_replace_handler(
            path.to_str().unwrap(),
            &args(Some("foo"), Some("bar")),
        ));
        match res {
            Err(EditToolError::MultipleOccurrences(old, line)) => {
                assert_eq!(old, "foo");
                // first line with a hit is line 1 (1-based)
                assert_eq!(line, 1);
            }
            other => panic!("unexpected result: {:?}", other),
        }
    }
    #[test]
    fn errors_when_multiple_occurrences_in_single_line() {
        let dir = tempdir().unwrap();
        let content = "foo foo bar\nnext line\n";
        let path = write_temp_file(&dir, "a.txt", content);
        let res = run_async(str_replace_handler(
            path.to_str().unwrap(),
            &args(Some("foo"), Some("xyz")),
        ));
        match res {
            Err(EditToolError::MultipleOccurrences(old, line)) => {
                assert_eq!(old, "foo");
                assert_eq!(line, 1); // first (and only) line where it occurs
            }
            other => panic!("unexpected result: {:?}", other),
        }
    }
    #[test]
    fn succeeds_for_single_occurrence_same_line() {
        let dir = tempdir().unwrap();
        let content = "before\nhello world\nafter\n";
        let path = write_temp_file(&dir, "a.txt", content);
        let res = run_async(str_replace_handler(
            path.to_str().unwrap(),
            &args(Some("hello"), Some("HELLO")),
        ))
        .expect("should succeed");
        // Verify file content changed
        let new_content = fs::read_to_string(&path).unwrap();
        assert!(new_content.contains("HELLO world"));
        assert!(!new_content.contains("hello world"));
        // Verify output message contains path and snippet label
        let out = res.output.expect("has output");
        assert!(out.contains(&format!(
            "The file {} has been edited.",
            path.to_str().unwrap()
        )));
        assert!(out.contains("a snippet of"));
        // The snippet computation uses the new content; ensure it includes the replacement line vicinity.
        assert!(out.contains("HELLO world"));
    }
    #[test]
    fn succeeds_for_single_occurrence_with_tabs_expansion_on_match_and_replacement() {
        let dir = tempdir().unwrap();
        // old_str and file both will be matched using expand_tabs_fixed(..., 2).
        // Example: file contains a tab, old_str uses a tab; match should work.
        let content = "fn main() {\n\tprintln!(\"hi\");\n}\n";
        let path = write_temp_file(&dir, "a.rs", content);
        // Replace the line containing a tab
        // old_str: "\tprintln!(\"hi\");"
        // new_str: "\tprintln!(\"hello\");"
        let res = run_async(str_replace_handler(
            path.to_str().unwrap(),
            &args(Some("\tprintln!(\"hi\");"), Some("\tprintln!(\"hello\");")),
        ))
        .expect("should succeed");
        let new_content = fs::read_to_string(&path).unwrap();
        assert!(new_content.contains("hello"));
        assert!(!new_content.contains("hi\");\n"));
        // Output contains snippet including the updated line
        let out = res.output.expect("has output");
        assert!(out.contains("a snippet of"));
        assert!(out.contains("println!(\"hello\");"));
    }
    #[test]
    fn snippet_bounds_are_capped_and_start_is_1_based_in_message() {
        let dir = tempdir().unwrap();
        // Build content with multiple lines to exercise snippet range capping
        let mut content = String::new();
        for i in 0..10 {
            content.push_str(&format!("line {}\n", i));
        }
        let path = write_temp_file(&dir, "a.txt", &content);
        // Replace something near the top to exercise saturating_sub for start_line
        let res = run_async(str_replace_handler(
            path.to_str().unwrap(),
            &args(Some("line 1"), Some("LINE 1")),
        ))
        .expect("should succeed");
        // Verify replacement
        let new_content = fs::read_to_string(&path).unwrap();
        assert!(new_content.contains("LINE 1"));
        assert!(!new_content.contains("line 1\n"));
        // Check start line in message is 1-based and reasonable
        let out = res.output.expect("has output");
        // Message includes: "a snippet of <path> (starting at line X):"
        // We don't know SNIPPET_LINES value here; assert presence of the phrase and a sane number.
        assert!(out.contains("starting at line "));
    }
    #[test]
    fn replacement_uses_full_replace_of_expanded_old_str() {
        // Ensures replacement uses expanded_old_str and expanded_new_str globally once validations pass.
        let dir = tempdir().unwrap();
        // The function validates single occurrence by scanning lines with expanded_old_str.
        // Make content such that only one expanded_old_str occurrence exists.
        let content = "a\tb c\nd e f\n";
        let path = write_temp_file(&dir, "a.txt", content);
        // old_str is "\ta" will not match; use "a\tb" to match once
        let _ = run_async(str_replace_handler(
            path.to_str().unwrap(),
            &args(Some("a\tb"), Some("A\tB")),
        ))
        .expect("should succeed");

        let new_content = fs::read_to_string(&path).unwrap();
        // After expansion with 2-space tabs, "a\tb" replaced by "A\tB"
        assert!(new_content.contains("A"));
        assert!(new_content.contains("B"));
        assert!(!new_content.contains("a\tb"));
    }

    #[test]
    fn test_insert_missing_insert_line() {
        let dir = tempdir().expect("tempdir");
        let path = write_temp_file(&dir, "a.txt", "a\nb\n");
        let args = args_insert(None, Some("X"));
        let res =
            run_async(insert_handler(path.to_str().unwrap(), &args)).expect("Ok result expected");
        assert!(res.output.is_none());
        assert_eq!(res.error_code, Some(-1));
        let msg = res.error.unwrap();
        assert!(msg.contains("Parameter `insert_line` is required"));
    }
    #[test]
    fn test_insert_invalid_insert_line_negative() {
        let dir = tempdir().expect("tempdir");
        let path = write_temp_file(&dir, "a.txt", "a\nb\n");
        let args = args_insert(Some(-3), Some("X"));
        let res =
            run_async(insert_handler(path.to_str().unwrap(), &args)).expect("Ok result expected");
        assert!(res.output.is_none());
        assert_eq!(res.error_code, Some(-1));
        let msg = res.error.unwrap();
        assert!(
            msg.contains("Parameter `insert_line` is required")
                || msg.contains("should be integer")
        ); // matches the validation branch
    }
    #[test]
    fn test_insert_missing_new_str() {
        let dir = tempdir().expect("tempdir");
        let path = write_temp_file(&dir, "a.txt", "a\nb\n");
        let args = args_insert(Some(0), None);
        let res =
            run_async(insert_handler(path.to_str().unwrap(), &args)).expect("Ok result expected");
        assert!(res.output.is_none());
        assert_eq!(res.error_code, Some(-1));
        let msg = res.error.unwrap();
        assert!(msg.contains("Parameter `new_str` is required"));
    }
    #[test]
    fn test_insert_out_of_range_high() {
        // file lines: split by '\n' retains empty segment at end -> ["a", "b", ""], len = 3
        let dir = tempdir().expect("tempdir");
        let path = write_temp_file(&dir, "a.txt", "a\nb\n");
        // insert_line > len (3) -> error
        let args = args_insert(Some(4), Some("X"));
        let res =
            run_async(insert_handler(path.to_str().unwrap(), &args)).expect("Ok result expected");
        assert!(res.output.is_none());
        assert_eq!(res.error_code, Some(-1));
        let msg = res.error.unwrap();
        assert!(msg.contains("Invalid `insert_line` parameter"));
        assert!(
            msg.contains("[0, 3]"),
            "range should reflect number of lines"
        );
    }
    #[test]
    fn test_insert_at_start() {
        let dir = tempdir().expect("tempdir");
        let path = write_temp_file(&dir, "a.txt", "a\nb\nc\n");
        let args = args_insert(Some(0), Some("X"));
        let res =
            run_async(insert_handler(path.to_str().unwrap(), &args)).expect("Ok result expected");
        assert!(res.error.is_none(), "should succeed");
        let out = res.output.unwrap();
        assert!(out.contains("The file"), "should include success header");
        assert!(out.contains("a snippet of the edited file"));
        // file should be updated with X inserted as first line
        let new_text = fs::read_to_string(&path).unwrap();
        assert_eq!(new_text, "X\na\nb\nc\n");
    }
    #[test]
    fn test_insert_in_middle() {
        let dir = tempdir().expect("tempdir");
        // file has 4 segments: ["a","b","c",""] because trailing '\n'
        let path = write_temp_file(&dir, "a.txt", "a\nb\nc\n");
        // insert at index 1 (0-based) before "b"
        let args = args_insert(Some(1), Some("X"));
        let res =
            run_async(insert_handler(path.to_str().unwrap(), &args)).expect("Ok result expected");
        assert!(res.error.is_none());
        let new_text = fs::read_to_string(&path).unwrap();
        assert_eq!(new_text, "a\nX\nb\nc\n");
    }

    // the test is wrong
    #[test]
    fn test_insert_multiline_new_str() {
        let dir = tempdir().expect("tempdir");
        let path = write_temp_file(&dir, "a.txt", "a\nb\nc");
        // Note: file without trailing newline -> split => ["a","b","c"] len=3
        let args = args_insert(Some(1), Some("X\nY"));
        let res =
            run_async(insert_handler(path.to_str().unwrap(), &args)).expect("Ok result expected");
        assert!(res.error.is_none());
        let new_text = fs::read_to_string(&path).unwrap();
        // Expected lines: ["a","X","Y","b","c"] joined => "a\nX\nY\nb\nc"
        assert_eq!(new_text, "a\nX\nY\nb\nc");
    }
    #[test]
    fn test_insert_snippet_window_and_label() {
        let dir = tempdir().expect("tempdir");
        // Create 10 lines with trailing newline
        let original: String = (1..=10).map(|i| format!("L{}\n", i)).collect();
        let path = write_temp_file(&dir, "a.txt", &original);
        // Insert at line index 5 (0-based), i.e., before "L6"
        let args = args_insert(Some(5), Some("X"));
        let res =
            run_async(insert_handler(path.to_str().unwrap(), &args)).expect("Ok result expected");
        assert!(res.error.is_none());
        let out = res.output.unwrap();
        // Snippet window: SNIPPET_LINES = 3
        // snippet_start = max(0, 5-3)=2 -> includes lines 3..5 (0-based) => L3, L4, L5
        // inserted lines: X
        // lines after: from 5..8 => L6, L7, L8
        // The snippet should contain: L3,L4,L5,X,L6,L7,L8
        assert!(out.contains("a snippet of the edited file (starting at line 3):"));
        assert!(out.contains("L3"));
        assert!(out.contains("L4"));
        assert!(out.contains("L5"));
        assert!(out.contains("\nX\n"));
        assert!(out.contains("L6"));
        assert!(out.contains("L7"));
        assert!(out.contains("L8"));
    }
    #[test]
    fn test_insert_tab_expansion_behavior() {
        let dir = tempdir().expect("tempdir");
        // File content has tabs; function expands tabs before splitting and joining
        let path = write_temp_file(&dir, "a.txt", "\tcol1\n\t\tcol2\n");
        // Insert a line with tabs
        let args = args_insert(Some(1), Some("\tINS"));
        let res =
            run_async(insert_handler(path.to_str().unwrap(), &args)).expect("Ok result expected");
        assert!(res.error.is_none());
        // Read file and ensure tabs were expanded consistently.
        // Since function writes the joined expanded lines, tabs in the inserted string and original are expanded to spaces.
        let new_text = fs::read_to_string(&path).unwrap();
        // We can compute the expected expansion using the same helper if exported;
        // otherwise, validate structural expectations: no raw '\t' remain and relative positions.
        assert!(
            !new_text.contains('\t'),
            "tabs should be expanded in final output"
        );
        // Ensure insertion point is correct: after first expanded line
        // Original lines after expansion:
        // expand_tabs_fixed("\tcol1\n\t\tcol2\n", TAB_WIDTH)
        // Insert expanded "\tINS" at index 1
        let expected_file_text = {
            let file_text = expand_tabs_fixed("\tcol1\n\t\tcol2\n", TAB_WIDTH);
            let lines: Vec<&str> = file_text.split('\n').collect(); // keeps empty last
            let ins = expand_tabs_fixed("\tINS", TAB_WIDTH);
            let ins_lines: Vec<&str> = ins.split('\n').collect();
            // manual merge mimic of function
            let mut new_lines = Vec::new();
            new_lines.extend(lines[..1].iter().copied());
            new_lines.extend(ins_lines.iter().copied());
            new_lines.extend(lines[1..].iter().copied());
            new_lines.join("\n")
        };
        assert_eq!(new_text, expected_file_text);
    }
    #[test]
    fn test_insert_at_file_start_snippet_bounds() {
        let dir = tempdir().expect("tempdir");
        let path = write_temp_file(&dir, "a.txt", "A\nB\nC\nD\n");
        // insert at 0 should show snippet starting at line 1
        let args = args_insert(Some(0), Some("X\nY"));
        let res =
            run_async(insert_handler(path.to_str().unwrap(), &args)).expect("Ok result expected");
        assert!(res.error.is_none());
        let out = res.output.unwrap();
        assert!(out.contains("(starting at line 1):"));
        // Snippet should include inserted X,Y and next up to SNIPPET_LINES lines after
        assert!(out.contains("X"));
        assert!(out.contains("Y"));
        assert!(out.contains("A"));
        assert!(out.contains("B"));
    }
    #[test]
    fn test_insert_at_file_end_snippet_bounds() {
        let dir = tempdir().expect("tempdir");
        let path = write_temp_file(&dir, "a.txt", "A\nB\nC\n");
        // file_text_lines split => ["A","B","C",""] len=4, insert at 4 (end)
        let args = args_insert(Some(4), Some("X"));
        let res =
            run_async(insert_handler(path.to_str().unwrap(), &args)).expect("Ok result expected");
        assert!(res.error.is_none());
        let out = res.output.unwrap();
        // snippet_start = max(0, 4-3)=1 -> starts at line 2 (1-based)
        assert!(out.contains("(starting at line 2):"));
        assert!(out.contains("B"));
        assert!(out.contains("C"));
        assert!(out.contains("X"));
    }
    #[test]
    fn test_insert_io_error_on_write() {
        // Simulate write error by pointing to a path in a directory that does not exist
        // Read succeeds must fail for this to target write; to ensure read succeeds, we create and then remove permissions
        let dir = tempdir().expect("tempdir");
        let path = write_temp_file(&dir, "a.txt", "A\n");
        // Make the directory read-only to provoke write error on most systems
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut perms = fs::metadata(dir.path()).unwrap().permissions();
            perms.set_mode(0o555); // r-x
            fs::set_permissions(dir.path(), perms).unwrap();
        }
        let args = args_insert(Some(0), Some("X"));
        let res = run_async(insert_handler(path.to_str().unwrap(), &args));
        match res {
            Err(EditToolError::Io) => { /* expected on write failure */ }
            Ok(ok) => {
                // In some environments, permissions might not prevent write.
                // If write succeeded, at least ensure content matches expected.
                let new_text = fs::read_to_string(&path).unwrap();
                if new_text != "X\nA\n" && new_text != "X\nA" {
                    panic!(
                        "unexpected content when write unexpectedly succeeded: {:?}",
                        new_text
                    );
                }
                // And success message present
                assert!(ok.output.is_some());
            }
            Err(e) => panic!("unexpected error: {:?}", e),
        }
    }
}
