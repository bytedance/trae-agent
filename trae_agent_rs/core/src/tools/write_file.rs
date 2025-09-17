use std::{collections::HashMap, fs};

use crate::{Tool, ToolExecResult};
use thiserror::Error;

#[derive(Default)]
pub struct WriteFile {}

impl Tool for WriteFile {
    fn get_name(&self) -> &str {
        "write_file"
    }

    fn reset(&mut self) {}

    fn get_description(&self) -> &str {
        "Create a new file or overwrite an existing file with the specified content."
    }

    fn get_input_schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the file to create or overwrite."
                },
                "content": {
                    "type": "string",
                    "description": "The content to write to the file."
                }
            },
            "required": ["path", "content"]
        })
    }

    fn get_descriptive_message(&self, arguments: &HashMap<String, serde_json::Value>) -> String {
        let path = arguments.get("path").and_then(|x| x.as_str()).unwrap_or("");
        format!("Writing file: {}", path)
    }

    fn needs_approval(&self, arguments: &HashMap<String, serde_json::Value>) -> bool {
        // If the old file exists, we need to ask for approval
        let path = arguments.get("path").and_then(|x| x.as_str()).unwrap_or("");
        if fs::metadata(path).is_ok() {
            return true;
        }
        false
    }

    fn execute(
        &mut self,
        arguments: HashMap<String, serde_json::Value>,
    ) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<String, String>> + Send + '_>>
    {
        Box::pin(async move {
            let path = arguments.get("path").and_then(|v| v.as_str()).unwrap_or("");
            let content = arguments
                .get("content")
                .and_then(|v| v.as_str())
                .unwrap_or("");

            if path.is_empty() {
                return Err("Path parameter is required".to_string());
            }

            match fs::write(path, content) {
                Ok(_) => Ok(format!("File created successfully at: {}", path)),
                Err(e) => Err(format!("Failed to write file: {}", e)),
            }
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;
    use serde_json::json;

    fn get_temp_direcotry() -> TempDir {
        TempDir::new().unwrap()
    }

    #[tokio::test]
    async fn test_write_file() {
        let mut write_file = WriteFile::default();
        let mut args = HashMap::new();
        let temp_dir = get_temp_direcotry();
        let path = temp_dir.path().join("test.txt");
        args.insert("path".to_string(), json!(path.to_string_lossy().to_string()));
        args.insert("content".to_string(), json!("Hello, world!"));
        let result = write_file.execute(args).await;
        assert_eq!(result.unwrap(), format!("File created successfully at: {}", path.to_string_lossy()));
        assert!(path.exists());
        assert_eq!(fs::read_to_string(path).unwrap(), "Hello, world!");
    }

    #[tokio::test]
    async fn test_write_file_already_exists() {
        let mut write_file = WriteFile::default();
        let mut args = HashMap::new();
        let temp_dir = get_temp_direcotry();
        let path = temp_dir.path().join("test.txt");
        fs::write(&path, "Hello, world!").unwrap();
        args.insert("path".to_string(), json!(path.to_string_lossy().to_string()));
        args.insert("content".to_string(), json!("New Content."));
        let result = write_file.execute(args).await;
        assert!(!result.is_err());
        assert_eq!(fs::read_to_string(path).unwrap(), "New Content.");
    }
}