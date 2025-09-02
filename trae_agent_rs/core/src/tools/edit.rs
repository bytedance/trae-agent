// the edcit tools is set to be here

use std::{collections::HashMap, fs, path::Path, process::Stdio};

use crate::{Tool, ToolExecResult};
use thiserror::Error;
use tokio::process::Command;

const EditCommand: [&str; 4] = ["view", "create", "str_replace", "insert"];

const SNIPPET_LINES: u32 = 4; //would u8 already enough ?

pub struct Edit {}

impl Tool for Edit {
    fn get_name(&self) -> &str {
        return "str_replace_based_edit_tool";
    }

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
                    "enum": EditCommand,
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
        &self,
        arguments: std::collections::HashMap<String, serde_json::Value>,
    ) -> std::pin::Pin<Box<dyn Future<Output = Result<String, String>> + Send + '_>> {
        todo!()
    }
}

async fn view_handler(args: HashMap<String, serde_json::Value>) {
    todo!()
}

fn create_handler() {
    todo!()
}

fn str_replace_handler() {
    todo!()
}

fn insert_handler() {
    todo!()
}

async fn view(path: &str, view_range: Option<&[&i32; 2]>) -> Result<ToolExecResult, EditToolError> {
    if Path::new(path).is_dir() {
        if view_range.is_none() {
            return Err(EditToolError::Other(
                "view range parameter is not allowed when path points to a directorys".to_string(),
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
            let stderr = {
                let res_err = String::from_utf8(res.stderr);

                if let Ok(error_msg) = res_err {
                    Some(error_msg);
                }
                None // fail to parse 
            };
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
        if *range[0] > *range[1] && *range[1] != -1 {
            return Err(EditToolError::IndexError(
                "Index one must be larger than index zero".to_string(),
            ));
        }

        if *range[1] > number_line as i32 || *range[0] > number_line as i32 {
            return Err(EditToolError::IndexError(
                "Index is larger than the total number of lines in the file".to_string(),
            ));
        }

        let file_lines: Vec<&str> = file_content.split("\n").collect();

        let file_slice: String;

        if *range[1] == -1 {
            file_slice = file_lines[*range[0] as usize..].join("\n");
        } else {
            file_slice = file_lines[*range[0] as usize..*range[1] as usize].join("\n");
        }

        //TODO: haven't hande cases like file_content and file_content tab

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
            output: Some(format!("The follow is the full content of the file: {} \n content: {} \n" ,path, file_content)), 
            error: None, 
            error_code: None
        })
    }


    Err(EditToolError::Other("Unexpected Error".to_string()))
}

#[derive(Error, Debug)]
enum EditToolError {
    #[error("invalid index number: {0}")]
    IndexError(String),

    #[error("fail to read the fiel")]
    FailReadFile,

    #[error("other error {0}")]
    Other(String),
}

#[cfg(test)]
mod tests {
    use super::*; // bring view, ToolExecResult, EditToolError into scope
    use std::fs;
    use std::path::Path;
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
        let range_arr: [&i32; 2] = [&2, &4];
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
        let range_arr: [&i32; 2] = [&1, &-1]; // from line 1 to end
        let result = run_async(view(path_str, Some(&range_arr)));

        match result {
            Ok(res) => {
                let out = res.output.expect("output present");
                dbg!(out.clone());
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
        let range_arr: [&i32; 2] = [&2, &1]; // start > end and end != -1 -> should be IndexError
        let result = run_async(view(path_str, Some(&range_arr)));

        match result {
            Err(EditToolError::IndexError(_)) => {}
            other => panic!("expected IndexError, got {:?}", other),
        }
    }
}
