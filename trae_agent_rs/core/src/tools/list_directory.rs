use std::{collections::HashMap, fs, path::Path};

use crate::{Tool, ToolExecResult};
use glob::glob;
use thiserror::Error;

#[derive(Default)]
pub struct ListDirectory {}

impl Tool for ListDirectory {
    fn get_name(&self) -> &str {
        "list_directory"
    }

    fn reset(&mut self) {}

    fn get_description(&self) -> &str {
        "List files and directories from a specified path with glob pattern support.
        * Supports wildcard `*` for matching any file/directory at current level
        * Supports recursive wildcard `**` for matching any file/directory at any depth
        * Optional `include` parameter for additional glob patterns to include
        * Optional `exclude` parameter for additional glob patterns to exclude
        "
    }

    fn get_input_schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to read. Supports wildcard `*` and recursive wildcard `**`. For example: '/home/user/*' or '/project/**/*.rs'"
                },
                "include": {
                    "type": "array",
                    "description": "Optional additional glob patterns for files and directories that need to be included in the matched paths",
                    "items": {
                        "type": "string"
                    }
                },
                "exclude": {
                    "type": "array",
                    "description": "Optional additional glob patterns for files and directories that need to be excluded from the matched paths",
                    "items": {
                        "type": "string"
                    }
                }
            },
            "required": ["path"]
        })
    }

    fn get_descriptive_message(&self, arguments: &HashMap<String, serde_json::Value>) -> String {
        let path = arguments.get("path").and_then(|x| x.as_str()).unwrap_or("");
        format!("Listing directory for path: {}", path)
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
            let path = match arguments.get("path").and_then(|v| v.as_str()) {
                Some(p) => p.to_string(),
                None => return Err("Path parameter is required and must be a string".to_string()),
            };

            if path.is_empty() {
                return Err("Path cannot be empty".to_string());
            }

            let include_patterns = arguments
                .get("include")
                .and_then(|v| v.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|v| v.as_str())
                        .map(|s| s.to_string())
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default();

            let exclude_patterns = arguments
                .get("exclude")
                .and_then(|v| v.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|v| v.as_str())
                        .map(|s| s.to_string())
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default();

            let result = list_directory(&path, &include_patterns, &exclude_patterns).await;

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
                        Ok("Directory listing completed successfully".to_string())
                    }
                }
                Err(e) => Err(format!("Tool execution failed: {}", e)),
            }
        })
    }
}

async fn list_directory(
    path: &str,
    include_patterns: &[String],
    exclude_patterns: &[String],
) -> Result<ToolExecResult, ListDirectoryError> {
    let mut all_entries: Vec<String> = Vec::new();
    let mut errors: Vec<String> = Vec::new();

    // Process the path pattern
    match process_path_pattern(path) {
        Ok(mut entries) => all_entries.append(&mut entries),
        Err(e) => errors.push(format!("Error processing '{}': {}", path, e)),
    }

    // Apply include patterns if specified
    if !include_patterns.is_empty() {
        let mut included_entries: Vec<String> = Vec::new();
        for include_pattern in include_patterns {
            match process_path_pattern(include_pattern) {
                Ok(mut entries) => included_entries.append(&mut entries),
                Err(e) => errors.push(format!(
                    "Error processing include pattern '{}': {}",
                    include_pattern, e
                )),
            }
        }

        // Keep only entries that match include patterns
        all_entries.retain(|entry| included_entries.iter().any(|included| included == entry));
    }

    // Apply exclude patterns if specified
    if !exclude_patterns.is_empty() {
        let mut excluded_entries: Vec<String> = Vec::new();
        for exclude_pattern in exclude_patterns {
            match process_path_pattern(exclude_pattern) {
                Ok(mut entries) => excluded_entries.append(&mut entries),
                Err(e) => errors.push(format!(
                    "Error processing exclude pattern '{}': {}",
                    exclude_pattern, e
                )),
            }
        }

        // Remove entries that match exclude patterns
        all_entries.retain(|entry| !excluded_entries.iter().any(|excluded| excluded == entry));
    }

    // Remove duplicates and sort
    all_entries.sort();
    all_entries.dedup();

    // Format output
    let mut output = String::new();

    if !errors.is_empty() {
        output.push_str("Warnings:\n");
        for error in &errors {
            output.push_str(&format!("  - {}\n", error));
        }
        output.push('\n');
    }

    if all_entries.is_empty() {
        output.push_str("No files or directories found matching the specified patterns.");
    } else {
        output.push_str(&format!("Found {} files/directories:\n", all_entries.len()));
        for entry in &all_entries {
            let path = Path::new(entry);
            let entry_type = if path.is_dir() { "DIR " } else { "FILE" };
            output.push_str(&format!("  [{}] {}\n", entry_type, entry));
        }
    }

    Ok(ToolExecResult {
        output: Some(output),
        error: if errors.is_empty() {
            None
        } else {
            Some(errors.join("; "))
        },
        error_code: None,
    })
}

fn process_path_pattern(pattern: &str) -> Result<Vec<String>, ListDirectoryError> {
    let mut entries = Vec::new();

    // Check if it's a glob pattern or a regular path
    if pattern.contains('*') || pattern.contains('?') || pattern.contains('[') {
        // Use glob pattern matching
        match glob(pattern) {
            Ok(paths) => {
                for entry in paths {
                    match entry {
                        Ok(path_buf) => {
                            if let Some(path_str) = path_buf.to_str() {
                                entries.push(path_str.to_string());
                            }
                        }
                        Err(e) => return Err(ListDirectoryError::GlobError(e.to_string())),
                    }
                }
            }
            Err(e) => return Err(ListDirectoryError::PatternError(e.to_string())),
        }
    } else {
        // Regular path - check if it exists
        let path = Path::new(pattern);
        if path.exists() {
            if path.is_dir() {
                // List directory contents
                match fs::read_dir(pattern) {
                    Ok(dir_entries) => {
                        for entry in dir_entries {
                            match entry {
                                Ok(dir_entry) => {
                                    if let Some(path_str) = dir_entry.path().to_str() {
                                        entries.push(path_str.to_string());
                                    }
                                }
                                Err(e) => return Err(ListDirectoryError::IoError(e.to_string())),
                            }
                        }
                    }
                    Err(e) => return Err(ListDirectoryError::IoError(e.to_string())),
                }
            } else {
                // Single file
                entries.push(pattern.to_string());
            }
        } else {
            return Err(ListDirectoryError::PathNotFound(pattern.to_string()));
        }
    }

    Ok(entries)
}

#[derive(Error, Debug)]
enum ListDirectoryError {
    #[error("path not found: {0}")]
    PathNotFound(String),

    #[error("I/O error: {0}")]
    IoError(String),

    #[error("glob pattern error: {0}")]
    PatternError(String),

    #[error("glob execution error: {0}")]
    GlobError(String),
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use tempfile::TempDir;

    // this function is used to setup a temporary directory for testing
    fn setup_temporary_directory() -> TempDir {
        let temp_dir = TempDir::new().unwrap();

        fs::create_dir_all(temp_dir.path().join("test_dir")).unwrap();
        fs::create_dir_all(temp_dir.path().join("test_dir2")).unwrap();
        fs::create_dir_all(temp_dir.path().join("test_dir3")).unwrap();
        fs::create_dir_all(temp_dir.path().join("test_dir4")).unwrap();
        fs::create_dir_all(temp_dir.path().join("test_dir5")).unwrap();
        fs::create_dir_all(temp_dir.path().join("test_dir6")).unwrap();
        fs::create_dir_all(temp_dir.path().join("test_dir7")).unwrap();

        fs::create_dir_all(temp_dir.path().join("foo_dir")).unwrap();
        fs::create_dir_all(temp_dir.path().join("foo_dir/sub_dir1")).unwrap();
        fs::create_dir_all(temp_dir.path().join("foo_dir/sub_dir2")).unwrap();
        fs::create_dir_all(temp_dir.path().join("foo_dir/sub_dir1/sub_sub_dir1")).unwrap();
        fs::create_dir_all(temp_dir.path().join("foo_dir/sub_dir1/sub_sub_dir2")).unwrap();

        fs::create_dir_all(temp_dir.path().join("test_dir/sub_dir1")).unwrap();
        fs::create_dir_all(temp_dir.path().join("test_dir/sub_dir2")).unwrap();
        fs::create_dir_all(temp_dir.path().join("test_dir/sub_dir1/sub_sub_dir1")).unwrap();
        fs::create_dir_all(temp_dir.path().join("test_dir/sub_dir1/sub_sub_dir2")).unwrap();

        // create some temp files in test_dir/sub_dir1/sub_sub_dir1
        fs::write(
            temp_dir
                .path()
                .join("test_dir/sub_dir1/sub_sub_dir1/file1.txt"),
            "file1",
        )
        .unwrap();
        fs::write(
            temp_dir
                .path()
                .join("test_dir/sub_dir1/sub_sub_dir1/file2.txt"),
            "file2",
        )
        .unwrap();
        fs::write(
            temp_dir
                .path()
                .join("test_dir/sub_dir1/sub_sub_dir1/file3.txt"),
            "file3",
        )
        .unwrap();
        fs::write(
            temp_dir
                .path()
                .join("test_dir/sub_dir1/sub_sub_dir1/file4.txt"),
            "file4",
        )
        .unwrap();
        fs::write(
            temp_dir
                .path()
                .join("test_dir/sub_dir1/sub_sub_dir1/file5.txt"),
            "file5",
        )
        .unwrap();
        fs::write(
            temp_dir
                .path()
                .join("test_dir/sub_dir1/sub_sub_dir1/file6.txt"),
            "file6",
        )
        .unwrap();

        temp_dir
    }

    #[tokio::test]
    async fn test_list_directory() {
        let mut list_directory = ListDirectory::default();
        let mut args = HashMap::new();
        let temp_dir = setup_temporary_directory();
        let path = temp_dir.path().to_string_lossy().to_string();
        args.insert("path".to_string(), json!(path));
        let result = list_directory.execute(args).await;
        assert!(result.is_ok());

        let content = result.unwrap();
        assert!(content.contains("test_dir"));
        assert!(content.contains("test_dir2"));
        assert!(content.contains("test_dir3"));
        assert!(content.contains("test_dir4"));
        assert!(content.contains("test_dir5"));
        assert!(content.contains("test_dir6"));
        assert!(content.contains("test_dir7"));
    }

    #[tokio::test]
    async fn test_list_directory_with_wildcard() {
        let mut list_directory = ListDirectory::default();
        let mut args = HashMap::new();
        let temp_dir = setup_temporary_directory();
        let path = temp_dir.path().join("foo_*").to_string_lossy().to_string();
        args.insert("path".to_string(), json!(path));
        let result = list_directory.execute(args).await;
        assert!(result.is_ok());
        let content = result.unwrap();
        assert!(content.contains("foo_dir"));

        assert!(!content.contains("test_dir"));
    }

    #[tokio::test]
    async fn test_list_directory_with_wildcard_and_sub_dir() {
        let mut list_directory = ListDirectory::default();
        let mut args = HashMap::new();
        let temp_dir = setup_temporary_directory();
        let path = temp_dir
            .path()
            .join("foo_*/*")
            .to_string_lossy()
            .to_string();
        args.insert("path".to_string(), json!(path));
        let result = list_directory.execute(args).await;
        assert!(result.is_ok());
        let content = result.unwrap();
        assert!(content.contains("foo_dir/sub_dir1"));
        assert!(content.contains("foo_dir/sub_dir2"));

        assert!(!content.contains("test_dir"));
    }

    #[tokio::test]
    async fn test_list_directory_with_wildcard_and_recursive() {
        let mut list_directory = ListDirectory::default();
        let mut args = HashMap::new();
        let temp_dir = setup_temporary_directory();
        let path = temp_dir
            .path()
            .join("foo_*/**")
            .to_string_lossy()
            .to_string();
        args.insert("path".to_string(), json!(path));
        let result = list_directory.execute(args).await;
        assert!(result.is_ok());
        let content = result.unwrap();
        assert!(content.contains("foo_dir"));
        assert!(content.contains("foo_dir/sub_dir1"));
        assert!(content.contains("foo_dir/sub_dir2"));
        assert!(content.contains("foo_dir/sub_dir1/sub_sub_dir1"));
        assert!(content.contains("foo_dir/sub_dir1/sub_sub_dir2"));
    }

    #[tokio::test]
    async fn test_list_directory_with_include() {
        let mut list_directory = ListDirectory::default();
        let mut args = HashMap::new();
        let temp_dir = setup_temporary_directory();
        let path = temp_dir
            .path()
            .join("test_*/**/*")
            .to_string_lossy()
            .to_string();
        let include_path = temp_dir
            .path()
            .join("test_dir/**/*.txt")
            .to_string_lossy()
            .to_string();
        args.insert("path".to_string(), json!(path));
        args.insert("include".to_string(), json!(vec![include_path]));
        let result = list_directory.execute(args).await;
        assert!(result.is_ok());
        let content = result.unwrap();

        assert!(content.contains("test_dir/sub_dir1/sub_sub_dir1/file1.txt"));
        assert!(content.contains("test_dir/sub_dir1/sub_sub_dir1/file2.txt"));
        assert!(content.contains("test_dir/sub_dir1/sub_sub_dir1/file3.txt"));
        assert!(content.contains("test_dir/sub_dir1/sub_sub_dir1/file4.txt"));
        assert!(content.contains("test_dir/sub_dir1/sub_sub_dir1/file5.txt"));
        assert!(content.contains("test_dir/sub_dir1/sub_sub_dir1/file6.txt"));
        assert!(!content.contains("test_dir/sub_dir2"));
    }

    #[tokio::test]
    async fn test_list_directory_with_exclude() {
        let mut list_directory = ListDirectory::default();
        let mut args = HashMap::new();
        let temp_dir = setup_temporary_directory();
        let path = temp_dir
            .path()
            .join("test_*/**/*")
            .to_string_lossy()
            .to_string();
        let exclude_path = temp_dir
            .path()
            .join("test_dir/**/*.txt")
            .to_string_lossy()
            .to_string();
        args.insert("path".to_string(), json!(path));
        args.insert("exclude".to_string(), json!(vec![exclude_path]));
        let result = list_directory.execute(args).await;
        assert!(result.is_ok());
        let content = result.unwrap();
        assert!(!content.contains("test_dir/sub_dir1/sub_sub_dir1/file1.txt"));
        assert!(!content.contains("test_dir/sub_dir1/sub_sub_dir1/file2.txt"));
        assert!(!content.contains("test_dir/sub_dir1/sub_sub_dir1/file3.txt"));
        assert!(!content.contains("test_dir/sub_dir1/sub_sub_dir1/file4.txt"));
        assert!(!content.contains("test_dir/sub_dir1/sub_sub_dir1/file5.txt"));
        assert!(!content.contains("test_dir/sub_dir1/sub_sub_dir1/file6.txt"));
        assert!(content.contains("test_dir/sub_dir2"));
    }

    #[tokio::test]
    async fn test_list_directory_with_include_and_exclude() {
        let mut list_directory = ListDirectory::default();
        let mut args = HashMap::new();
        let temp_dir = setup_temporary_directory();
        let path = temp_dir
            .path()
            .join("test_*/**/*")
            .to_string_lossy()
            .to_string();
        let include_path = temp_dir
            .path()
            .join("test_dir/**/*.txt")
            .to_string_lossy()
            .to_string();
        let exclude_path = temp_dir
            .path()
            .join("test_dir/**/file1.txt")
            .to_string_lossy()
            .to_string();
        args.insert("path".to_string(), json!(path));
        args.insert("include".to_string(), json!(vec![include_path]));
        args.insert("exclude".to_string(), json!(vec![exclude_path]));
        let result = list_directory.execute(args).await;
        assert!(result.is_ok());
        let content = result.unwrap();

        assert!(!content.contains("test_dir/sub_dir1/sub_sub_dir1/file1.txt"));
        assert!(content.contains("test_dir/sub_dir1/sub_sub_dir1/file2.txt"));
        assert!(content.contains("test_dir/sub_dir1/sub_sub_dir1/file3.txt"));
        assert!(content.contains("test_dir/sub_dir1/sub_sub_dir1/file4.txt"));
        assert!(content.contains("test_dir/sub_dir1/sub_sub_dir1/file5.txt"));
        assert!(content.contains("test_dir/sub_dir1/sub_sub_dir1/file6.txt"));
    }
}
