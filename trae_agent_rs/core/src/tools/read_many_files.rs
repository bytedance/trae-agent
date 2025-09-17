use std::{collections::HashMap, fs, path::Path};

use crate::{Tool, ToolExecResult};
use glob::glob;
use thiserror::Error;

#[derive(Default)]
pub struct ReadManyFiles {}

impl Tool for ReadManyFiles {
    fn get_name(&self) -> &str {
        "read_many_files"
    }

    fn reset(&mut self) {}

    fn get_description(&self) -> &str {
        "Read the contents of multiple files using glob patterns.
        * Supports wildcard `*` and recursive wildcard `**` patterns
        * Optional include/exclude patterns for additional filtering
        * Returns content of all matching files
        "
    }

    fn get_input_schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "description": "List of file paths or glob patterns to read. Supports wildcard `*` and recursive wildcard `**`.",
                    "items": {
                        "type": "string"
                    },
                    "minItems": 1
                },
                "include": {
                    "type": "array",
                    "description": "Optional additional glob patterns for files that should be included in the matched paths.",
                    "items": {
                        "type": "string"
                    }
                },
                "exclude": {
                    "type": "array",
                    "description": "Optional additional glob patterns for files that should be excluded from the matched paths.",
                    "items": {
                        "type": "string"
                    }
                },
                "max_files": {
                    "type": "integer",
                    "description": "Maximum number of files to read. Defaults to 50.",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 100
                }
            },
            "required": ["paths"]
        })
    }

    fn get_descriptive_message(&self, arguments: &HashMap<String, serde_json::Value>) -> String {
        let paths = arguments
            .get("paths")
            .and_then(|v| v.as_array())
            .map(|arr| arr.len())
            .unwrap_or(0);
        format!("Reading multiple files from {} path patterns", paths)
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
            let paths = arguments
                .get("paths")
                .and_then(|v| v.as_array())
                .ok_or("Paths parameter is required and must be an array")?;

            let include_patterns = arguments
                .get("include")
                .and_then(|v| v.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|v| v.as_str())
                        .map(|s| s.to_string())
                        .collect::<Vec<String>>()
                })
                .unwrap_or_default();

            let exclude_patterns = arguments
                .get("exclude")
                .and_then(|v| v.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|v| v.as_str())
                        .map(|s| s.to_string())
                        .collect::<Vec<String>>()
                })
                .unwrap_or_default();

            let max_files = arguments
                .get("max_files")
                .and_then(|v| v.as_i64())
                .unwrap_or(50) as usize;

            let path_patterns: Vec<String> = paths
                .iter()
                .filter_map(|v| v.as_str())
                .map(|s| s.to_string())
                .collect();

            if path_patterns.is_empty() {
                return Err("At least one path pattern is required".to_string());
            }

            let result =
                read_many_files(path_patterns, include_patterns, exclude_patterns, max_files).await;

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
                        Ok("Files read successfully".to_string())
                    }
                }
                Err(e) => Err(format!("Tool execution failed: {}", e)),
            }
        })
    }
}

async fn read_many_files(
    path_patterns: Vec<String>,
    include_patterns: Vec<String>,
    exclude_patterns: Vec<String>,
    max_files: usize,
) -> Result<ToolExecResult, ReadManyFilesError> {
    let mut all_files = Vec::new();

    // Collect files from all path patterns
    for pattern in &path_patterns {
        match glob(pattern) {
            Ok(paths) => {
                for entry in paths {
                    match entry {
                        Ok(path) => {
                            if path.is_file() {
                                all_files.push(path);
                            }
                        }
                        Err(e) => {
                            return Err(ReadManyFilesError::GlobError(e.to_string()));
                        }
                    }
                }
            }
            Err(e) => {
                return Err(ReadManyFilesError::PatternError(e.to_string()));
            }
        }
    }

    // Apply include patterns
    if !include_patterns.is_empty() {
        let mut included_files = Vec::new();
        for include_pattern in &include_patterns {
            match glob(include_pattern) {
                Ok(paths) => {
                    for entry in paths.flatten() {
                        if entry.is_file() && all_files.contains(&entry) {
                            included_files.push(entry);
                        }
                    }
                }
                Err(e) => {
                    return Err(ReadManyFilesError::PatternError(e.to_string()));
                }
            }
        }
        all_files = included_files;
    }

    // Apply exclude patterns
    for exclude_pattern in &exclude_patterns {
        match glob(exclude_pattern) {
            Ok(paths) => {
                for entry in paths.flatten() {
                    if entry.is_file() {
                        all_files.retain(|f| f != &entry);
                    }
                }
            }
            Err(e) => {
                return Err(ReadManyFilesError::PatternError(e.to_string()));
            }
        }
    }

    // Remove duplicates and limit files
    all_files.sort();
    all_files.dedup();
    all_files.truncate(max_files);

    if all_files.is_empty() {
        return Ok(ToolExecResult {
            output: Some("No files matched the specified patterns.".to_string()),
            error: None,
            error_code: None,
        });
    }

    let mut output = String::new();
    output.push_str(&format!("Reading {} files:\n\n", all_files.len()));

    for (index, file_path) in all_files.iter().enumerate() {
        let path_str = file_path.to_string_lossy();
        output.push_str(&format!("=== File {}: {} ===\n", index + 1, path_str));

        match fs::read_to_string(file_path) {
            Ok(content) => {
                if content.len() > 10000 {
                    output.push_str(&format!(
                        "{}\n[Content truncated - file is {} bytes]\n\n",
                        &content[..10000],
                        content.len()
                    ));
                } else {
                    output.push_str(&content);
                    output.push_str("\n\n");
                }
            }
            Err(e) => {
                output.push_str(&format!("Error reading file: {}\n\n", e));
            }
        }
    }

    Ok(ToolExecResult {
        output: Some(output),
        error: None,
        error_code: None,
    })
}

#[derive(Error, Debug)]
enum ReadManyFilesError {
    #[error("glob pattern error: {0}")]
    PatternError(String),

    #[error("glob execution error: {0}")]
    GlobError(String),
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;
    use serde_json::json;

    fn prepare_test_file() -> TempDir {
        let temp_dir = TempDir::new().unwrap();
        let temp_path = temp_dir.path().join("test.txt");
        let path = temp_path.to_str().unwrap();
        fs::write(path, "1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n").unwrap();
        let temp_path2 = temp_dir.path().join("test2.txt");
        let path2 = temp_path2.to_str().unwrap();
        fs::write(path2, "11\n12\n13\n14\n15\n16\n17\n18\n19\n20\n").unwrap();
        temp_dir
    }

    #[tokio::test]
    async fn test_read_many_files() {
        let mut read_many_files = ReadManyFiles::default();
        let mut args = HashMap::new();
        let temp_dir = prepare_test_file();
        let path1 = temp_dir.path().join("test.txt").to_string_lossy().to_string();
        let path2 = temp_dir.path().join("test2.txt").to_string_lossy().to_string();
        args.insert("paths".to_string(), json!(vec![path1, path2]));
        let result = read_many_files.execute(args).await;
        assert!(result.is_ok());
        let content = result.unwrap();

        assert!(content.contains("1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n"));
        assert!(content.contains("11\n12\n13\n14\n15\n16\n17\n18\n19\n20\n"));
    }

    #[tokio::test]
    async fn test_read_many_files_with_include() {
        let mut read_many_files = ReadManyFiles::default();
        let mut args = HashMap::new();
        let temp_dir = prepare_test_file();
        let path = temp_dir.path().join("*.txt").to_string_lossy().to_string();
        let include_path = temp_dir.path().join("test2.txt").to_string_lossy().to_string();
        args.insert("paths".to_string(), json!(vec![path]));
        args.insert("include".to_string(), json!(vec![include_path]));
        let result = read_many_files.execute(args).await;
        assert!(result.is_ok());
        let content = result.unwrap();
        assert!(content.contains("11\n12\n13\n14\n15\n16\n17\n18\n19\n20\n"));
        assert!(!content.contains("1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n"));
    }

    #[tokio::test]
    async fn test_read_many_files_with_exclude() {
        let mut read_many_files = ReadManyFiles::default();
        let mut args = HashMap::new();
        let temp_dir = prepare_test_file();
        let path = temp_dir.path().join("*.txt").to_string_lossy().to_string();
        let exclude_path = temp_dir.path().join("test2.txt").to_string_lossy().to_string();
        args.insert("paths".to_string(), json!(vec![path]));
        args.insert("exclude".to_string(), json!(vec![exclude_path]));
        let result = read_many_files.execute(args).await;
        assert!(result.is_ok());
        let content = result.unwrap();
        assert!(!content.contains("11\n12\n13\n14\n15\n16\n17\n18\n19\n20\n"));
        assert!(content.contains("1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n"));
    }

}