use std::{collections::HashMap, fs, path::Path};

use crate::{Tool, ToolExecResult};
use thiserror::Error;

#[derive(Default)]
pub struct ReadFile {}

impl Tool for ReadFile {
    fn get_name(&self) -> &str {
        "read_file"
    }

    fn reset(&mut self) {}

    fn get_description(&self) -> &str {
        "Read the contents of a single file at the specified path.
        * If `path` is a file, displays the complete file contents
        * If `path` is a directory, returns an error
        * Supports optional `view_range` parameter to read specific line ranges
        "
    }

    fn get_input_schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the file to read, e.g. `/repo/file.py`."
                },
                "view_range": {
                    "type": "array",
                    "description": "Optional parameter to read specific line ranges. If provided, the file will be shown in the indicated line number range, e.g. [11, 12] will show lines 11 and 12. Indexing starts at 1. Setting `[start_line, -1]` shows all lines from `start_line` to the end of the file.",
                    "items": {
                        "type": "integer"
                    },
                    "minItems": 2,
                    "maxItems": 2
                }
            },
            "required": ["path"]
        })
    }

    fn get_descriptive_message(&self, arguments: &HashMap<String, serde_json::Value>) -> String {
        let path = arguments.get("path").and_then(|x| x.as_str()).unwrap_or("");
        format!("Reading file: {}", path)
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

            if path.is_empty() {
                return Err("Path parameter is required".to_string());
            }

            let view_range: Option<[i32; 2]> = arguments.get("view_range").and_then(|v| match v {
                serde_json::Value::Array(arr) if arr.len() == 2 => {
                    let a = arr[0].as_i64()? as i32;
                    let b = arr[1].as_i64()? as i32;
                    Some([a, b])
                }
                _ => None,
            });

            let result = read_file(path, view_range.as_ref()).await;

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
                        Ok("File read successfully".to_string())
                    }
                }
                Err(e) => Err(format!("Tool execution failed: {}", e)),
            }
        })
    }
}

async fn read_file(
    path: &str,
    view_range: Option<&[i32; 2]>,
) -> Result<ToolExecResult, ReadFileError> {
    if Path::new(path).is_dir() {
        return Err(ReadFileError::IsDirectory);
    }

    let file_content = fs::read_to_string(path).map_err(|_| ReadFileError::FailReadFile)?;

    let number_lines = file_content.chars().filter(|&c| c == '\n').count() + 1;

    if let Some(range) = view_range {
        if range[0] > range[1] && range[1] != -1 {
            return Err(ReadFileError::IndexError(
                "Start line must be less than or equal to end line".to_string(),
            ));
        }

        if range[1] > number_lines as i32 || range[0] > number_lines as i32 {
            return Err(ReadFileError::IndexError(
                "Line number is larger than the total number of lines in the file".to_string(),
            ));
        }

        if range[0] < 1 {
            return Err(ReadFileError::IndexError(
                "Line numbers must start from 1".to_string(),
            ));
        }

        let file_lines: Vec<&str> = file_content.split('\n').collect();

        let file_slice: String = if range[1] == -1 {
            file_lines[(range[0] as usize - 1)..].join("\n")
        } else {
            file_lines[(range[0] as usize - 1)..(range[1] as usize)].join("\n")
        };

        return Ok(ToolExecResult {
            output: Some(format!(
                "Here's the result of reading {} (lines {}-{}):\n{}\n",
                path,
                range[0],
                if range[1] == -1 {
                    number_lines as i32
                } else {
                    range[1]
                },
                file_slice
            )),
            error: None,
            error_code: None,
        });
    }

    Ok(ToolExecResult {
        output: Some(format!(
            "Here's the full content of the file: {}\n{}\n",
            path, file_content
        )),
        error: None,
        error_code: None,
    })
}

#[derive(Error, Debug)]
enum ReadFileError {
    #[error("invalid line range: {0}")]
    IndexError(String),

    #[error("failed to read the file")]
    FailReadFile,

    #[error("path points to a directory, not a file")]
    IsDirectory,
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    fn prepare_test_file() -> TempDir {
        let temp_dir = TempDir::new().unwrap();
        let temp_path = temp_dir.path().join("test.txt");
        let path = temp_path.to_str().unwrap();
        fs::write(path, "1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n").unwrap();
        temp_dir
    }

    #[tokio::test]
    async fn test_read_file_with_view_range() {
        let mut read_file = ReadFile::default();
        let mut args = HashMap::new();
        let temp_dir = prepare_test_file();
        let path = temp_dir.path().join("test.txt").to_string_lossy().to_string();
        args.insert("path".to_string(), serde_json::json!(path));
        args.insert("view_range".to_string(), serde_json::json!([1, 2]));
        let result = read_file.execute(args).await;
        assert_eq!(result.unwrap(), format!("Here's the result of reading {} (lines 1-2):\n1\n2\n", path));
    }

    #[tokio::test]
    async fn test_read_file_without_view_range() {
        let mut read_file = ReadFile::default();
        let mut args = HashMap::new();
        let temp_dir = prepare_test_file();
        let path = temp_dir.path().join("test.txt").to_string_lossy().to_string();
        args.insert("path".to_string(), serde_json::json!(path));
        let result = read_file.execute(args).await;
        assert_eq!(result.unwrap(), format!("Here's the full content of the file: {}\n1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n\n", path));
    }

    #[tokio::test]
    async fn test_read_file_with_view_range_out_of_bounds() {
        let mut read_file = ReadFile::default();
        let mut args = HashMap::new();
        let temp_dir = prepare_test_file();
        let path = temp_dir.path().join("test.txt").to_string_lossy().to_string();
        args.insert("path".to_string(), serde_json::json!(path));
        args.insert("view_range".to_string(), serde_json::json!([1, 100]));
        let result = read_file.execute(args).await;

        // expect an `Err` value
        assert!(result.is_err());

        // expect an error message containing "Line number is larger than the total number of lines in the file"
        if let Err(msg) = result {
            assert!(msg.contains("Tool execution failed: invalid line range: Line number is larger than the total number of lines in the file"));
        } else {
            panic!("Expected error message containing 'Line number is larger than the total number of lines in the file'");
        }
    }
}