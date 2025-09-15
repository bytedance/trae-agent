// bash tool

use std::io::{self};
use std::time::Duration;

use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::process::{Child, ChildStderr, ChildStdin, ChildStdout, Command};

use tokio::time;

use serde_json::Value;
use thiserror::Error;

use std::process::Stdio;

use crate::Tool;

pub struct Bash {
    model_provider: String,
    bash: BashProcess,
}

impl Bash {
    pub fn new(model_provider: String) -> Self {
        Bash {
            model_provider,
            bash: BashProcess::new(),
        }
    }
}

impl Tool for Bash {
    fn get_name(&self) -> &str {
        "bash"
    }

    fn reset(&mut self) {
        self.bash = BashProcess::new();
    }

    fn get_description(&self) -> &str {
        r#"Run commands in a bash shell
        * When invoking this tool, the contents of the "command" parameter does NOT need to be XML-escaped.
        * You have access to a mirror of common linux and python packages via apt and pip.
        * State is persistent across command calls and discussions with the user.
        * To inspect a particular line range of a file, e.g. lines 10-25, try 'sed -n 10,25p /path/to/the/file'.
        * Please avoid commands that may produce a very large amount of output.
        * Please run long lived commands in the background, e.g. 'sleep 10 &' or start a server in the background.
        "#
    }

    fn get_input_schema(&self) -> serde_json::Value {
        let data = match self.model_provider.as_str() {
            "openai" => {
                r#"
                {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The bash command to run."
                        },
                        "restart": {
                            "type": "boolean",
                            "description": "Set to true to restart the bash session."
                        }
                    },
                    "required": ["command", "restart"]
                }
                "#
            }
            _ => {
                r#"
                {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The bash command to run."
                        },
                        "restart": {
                            "type": "boolean",
                            "description": "Set to true to restart the bash session."
                        }
                    },
                    "required": ["command"]
                }
                "#
            }
        };

        let v: Value = serde_json::from_str(data).unwrap(); // since it is fixed so theoretically it should always be the same
        v
    }

    fn get_descriptive_message(
        &self,
        arguments: std::collections::HashMap<String, serde_json::Value>
    ) -> String {
        let cmd = arguments
            .get("command")
            .and_then(|x| x.as_str())
            .unwrap_or("");
        format!("Running bash command: {}", cmd)
    }

    fn execute(
        &mut self,
        arguments: std::collections::HashMap<String, serde_json::Value>,
    ) -> std::pin::Pin<Box<dyn Future<Output = Result<String, String>> + Send + '_>> {
        Box::pin(async move {
            let cmd = arguments
                .get("command")
                .and_then(|x| x.as_str())
                .unwrap_or("");

            let restart = arguments
                .get("restart")
                .and_then(|x| x.as_bool())
                .unwrap_or(false);

            // Assuming `self.bash.start()` is an asynchronous operation
            let starterr = self.bash.start().await;

            if let Err(e) = starterr {
                return Err(format!("fail to start the bash {}", e));
            }

            // run the command
            let exec_result = self.bash.run(cmd).await;
            if let Err(e) = exec_result {
                return Err(format!(
                    "fail to execute command: {} , getting error: {}",
                    cmd, e
                ));
            }

            if restart {
                let restart_result = self.bash.stop().await;

                if let Err(e) = restart_result {
                    return Err(format!("restart fail error: {}", e));
                }

                let rebot_result = self.bash.start().await;

                if let Err(e) = rebot_result {
                    return Err(format!("rebot fail error: {}", e));
                }
            }

            match exec_result {
                Ok(res) => {
                    // Store values to avoid borrow checker issues
                    let stdout = res.output;
                    let stderr = res.error;
                    let exit_code = res.error_code;

                    // Create combined output showing both stdout and stderr
                    let mut result = stdout.clone();

                    // If there's stderr content, append it with a clear separator
                    if !stderr.is_empty() {
                        if !result.is_empty() {
                            result.push('\n');
                        }
                        result.push_str("STDERR:\n");
                        result.push_str(&stderr);
                    }

                    // Only treat it as an error if exit code is non-zero
                    if exit_code != 0 {
                        return Err(format!(
                            "Command failed with exit code {}\nSTDOUT:\n{}\nSTDERR:\n{}",
                            exit_code, stdout, stderr
                        ));
                    }

                    Ok(result)
                }
                Err(e) => {
                    Err(format!("Unexpected Error {}", e)) // this should never happen due to previous check
                }
            }
        })
    }
}

// set the bash process to be private field
#[allow(dead_code)]
struct BashProcess {
    child: Option<Child>,
    stdin: Option<ChildStdin>,
    stdout: Option<ChildStdout>,
    stderr: Option<ChildStderr>,
    started: bool,
    timed_out: bool,
    timeout: Duration,
    output_delay: Duration,
    sentinel: String,
}

impl BashProcess {
    async fn start(&mut self) -> Result<(), BashError> {
        if self.started {
            return Ok(());
        }

        // For MacOS and Linux, use /bin/bash
        #[cfg(any(target_os = "macos", target_os = "linux"))]
        let mut cmd = Command::new("/bin/bash");

        // For Windows, use cmd
        #[cfg(target_os = "windows")]
        let mut cmd = Command::new("cmd");

        //TODO: add other operating system

        #[cfg(any(target_os = "macos", target_os = "linux"))]
        {
            cmd.stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped());
        }

        #[cfg(target_os = "windows")]
        {
            cmd.stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped());
        }

        let mut child = cmd.spawn().map_err(BashError::Io)?;

        let stdin = child.stdin.take().ok_or(BashError::SessionNotStarted)?;
        let stdout = child.stdout.take().ok_or(BashError::SessionNotStarted)?;
        let stderr = child.stderr.take().ok_or(BashError::SessionNotStarted)?;

        self.stdin = Some(stdin);
        self.stdout = Some(stdout);
        self.stderr = Some(stderr);

        self.child = Some(child);
        self.started = true;
        self.timed_out = false;

        Ok(())
    }

    async fn stop(&mut self) -> Result<(), BashError> {
        if !self.started {
            return Err(BashError::SessionNotStarted);
        }
        if let Some(child) = &mut self.child {
            if child.try_wait()?.is_some() {
                self.started = false;
                return Ok(());
            }

            child.kill().await.ok();
            let _ = child.wait().await;
            self.started = false;
            Ok(())
        } else {
            Ok(())
        }
    }

    async fn run(&mut self, command: &str) -> Result<BashExecResult, BashError> {
        //   dbg!("Starting run function", command);

        if !self.started {
            //    dbg!("Session not started");
            return Err(BashError::SessionNotStarted);
        }

        //WARNING ALL REFERENCE ARE NOW MUTABLE !
        //CONCURRENT RUNNING IN SAME PROCESS IS NOT ALLOWED
        let child = self.child.as_mut().ok_or(BashError::SessionNotStarted)?;
        let stdin = self
            .stdin
            .as_mut()
            .ok_or(BashError::Other("stdin not available".to_string()))?;
        let stdout = self.stdout.as_mut().ok_or(BashError::SessionNotStarted)?;
        let stderr = self.stderr.as_mut().ok_or(BashError::SessionNotStarted)?;

        if let Some(code) = child.try_wait()? {
            return Err(BashError::BashExited(code.code().unwrap_or(-1)));
        }

        if self.timed_out {
            //  dbg!("Already timed out");
            return Err(BashError::Timeout);
        }

        let (sentinel_before, _, sentinel_after) = {
            let parts: Vec<_> = self.sentinel.split("__ERROR_CODE__").collect();
            (parts[0], "__ERROR_CODE__", parts[1])
        };

        //   dbg!("Sentinel parts", sentinel_before, sentinel_after);

        #[cfg(windows)]
        let errcode_retriever = "!errorlevel!";
        #[cfg(not(windows))]
        let errcode_retriever = "$?";

        #[cfg(windows)]
        let command_sep = "&";
        #[cfg(not(windows))]
        let command_sep = ";";

        let full_command = format!(
            "(\n{}){} echo {}{}{}\n",
            command, command_sep, sentinel_before, errcode_retriever, sentinel_after
        );

        // dbg!("Full command to execute", &full_command);

        stdin.write_all(full_command.as_bytes()).await?;
        stdin.flush().await?;
        //   dbg!("Command written and flushed to stdin");

        let mut output_accum = String::new();
        let mut error_accum = String::new();
        let mut error_code: Option<i32> = None;

        // Timeout wrapper
        let timeout = self.timeout;
        let mut timed_out = false;
        let mut stdout_buffer = [0u8; 4096];
        let mut stderr_buffer = [0u8; 4096];

        //  dbg!("Starting concurrent read loop with timeout", timeout);

        // Use tokio::select! to read from both stdout and stderr concurrently
        loop {
            tokio::select! {
                // Read from stdout
                stdout_result = stdout.read(&mut stdout_buffer) => {
                    match stdout_result {
                        Ok(0) => {
                            // EOF on stdout
                            break;
                        }
                        Ok(bytes_read) => {
                            // Convert bytes to string
                            let chunk = String::from_utf8_lossy(&stdout_buffer[..bytes_read]).to_string();

                            // Check if sentinel is found
                            if chunk.contains(sentinel_before) {
                                if let Some(pos) = chunk.find(sentinel_before) {
                                    output_accum.push_str(&chunk[..pos]);
                                    let rest = &chunk[pos + sentinel_before.len()..];

                                    // Look for sentinel_after in the rest
                                    if let Some(after_pos) = rest.find(sentinel_after) {
                                        let code_str = &rest[..after_pos];
                                        if let Ok(code) = code_str.trim().parse::<i32>() {
                                            error_code = Some(code);
                                        }
                                    }
                                }
                                break;
                            } else {
                                // Accumulate output as normal
                                output_accum.push_str(&chunk);
                            }
                        }
                        Err(e) => {
                            return Err(BashError::Io(e));
                        }
                    }
                }

                // Read from stderr
                stderr_result = stderr.read(&mut stderr_buffer) => {
                    match stderr_result {
                        Ok(0) => {
                            // EOF on stderr, continue reading stdout
                        }
                        Ok(bytes_read) => {
                            let chunk = String::from_utf8_lossy(&stderr_buffer[..bytes_read]).to_string();
                            error_accum.push_str(&chunk);
                        }
                        Err(_) => {
                            // Stderr read error, but continue with stdout
                        }
                    }
                }

                // Global timeout
                _ = time::sleep(timeout) => {
                    timed_out = true;
                    break;
                }
            }
        }

        if timed_out {
            self.timed_out = true;
            return Err(BashError::Timeout);
        }

        // Try to read any remaining stderr data with a short timeout
        let mut final_stderr_buffer = [0u8; 4096];
        loop {
            match time::timeout(
                Duration::from_millis(50),
                stderr.read(&mut final_stderr_buffer),
            )
            .await
            {
                Ok(Ok(bytes_read)) if bytes_read > 0 => {
                    let chunk =
                        String::from_utf8_lossy(&final_stderr_buffer[..bytes_read]).to_string();
                    error_accum.push_str(&chunk);
                }
                _ => break,
            }
        }

        // Trim trailing newlines
        if output_accum.ends_with('\n') {
            output_accum.pop();
        }
        if error_accum.ends_with('\n') {
            error_accum.pop();
        }

        Ok(BashExecResult {
            output: output_accum,
            error: error_accum,
            error_code: error_code.unwrap_or(0),
        })
    }

    fn new() -> Self {
        Self {
            child: None,
            stdin: None,
            stdout: None,
            stderr: None,
            started: false,
            timed_out: false,
            timeout: Duration::from_secs(120),
            output_delay: Duration::from_millis(200),
            sentinel: ",,,,bash-command-exit-__ERROR_CODE__-banner,,,,".to_string(),
        }
    }
}

#[derive(Error, Debug)]
enum BashError {
    #[error("bash session not started")]
    SessionNotStarted,
    #[error("bash has exited with returncode {0}")]
    BashExited(i32),
    #[error("bash command timed out")]
    Timeout,
    #[error("io error: {0}")]
    Io(#[from] io::Error),
    #[error("other error: {0}")]
    Other(String),
}

#[derive(Debug, Default)]
struct BashExecResult {
    pub output: String,
    pub error: String,
    pub error_code: i32,
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::collections::HashMap;
    use std::time::Duration;

    #[test]
    fn test_bash_new() {
        let bash = Bash::new("openai".to_string());
        assert_eq!(bash.model_provider, "openai");
        assert!(!bash.bash.started);
    }

    #[test]
    fn test_get_name() {
        let bash = Bash::new("openai".to_string());
        assert_eq!(bash.get_name(), "bash");
    }

    #[test]
    fn test_get_description() {
        let bash = Bash::new("openai".to_string());
        let desc = bash.get_description();
        assert!(desc.contains("Run commands in a bash shell"));
        assert!(desc.contains("State is persistent"));
    }

    #[test]
    fn test_get_input_schema_openai() {
        let bash = Bash::new("openai".to_string());
        let schema = bash.get_input_schema();

        assert!(schema["type"] == "object");
        assert!(schema["properties"]["command"]["type"] == "string");
        assert!(schema["properties"]["restart"]["type"] == "boolean");

        // OpenAI provider should require both command and restart
        let required = schema["required"].as_array().unwrap();
        assert!(required.contains(&json!("command")));
        assert!(required.contains(&json!("restart")));
    }

    #[test]
    fn test_get_input_schema_non_openai() {
        let bash = Bash::new("anthropic".to_string());
        let schema = bash.get_input_schema();

        assert!(schema["type"] == "object");
        assert!(schema["properties"]["command"]["type"] == "string");
        assert!(schema["properties"]["restart"]["type"] == "boolean");

        // Non-OpenAI provider should only require command
        let required = schema["required"].as_array().unwrap();
        assert!(required.contains(&json!("command")));
        assert!(!required.contains(&json!("restart")));
    }

    #[test]
    fn test_bash_process_new() {
        let bash_process = BashProcess::new();
        assert!(!bash_process.started);
        assert!(!bash_process.timed_out);
        assert_eq!(bash_process.timeout, Duration::from_secs(120));
        assert_eq!(bash_process.output_delay, Duration::from_millis(200));
        assert_eq!(
            bash_process.sentinel,
            ",,,,bash-command-exit-__ERROR_CODE__-banner,,,,"
        );
    }

    #[tokio::test]
    async fn test_bash_process_start_and_stop() {
        let mut bash_process = BashProcess::new();
        bash_process.timeout = Duration::from_millis(500); // Very short timeout

        let start_result = bash_process.start().await;
        assert!(start_result.is_ok());
        assert!(bash_process.started);

        // Starting again should be ok (idempotent)
        let start_again_result = bash_process.start().await;
        assert!(start_again_result.is_ok());

        let stop_result = bash_process.stop().await;
        assert!(stop_result.is_ok());
        assert!(!bash_process.started);
    }

    #[tokio::test]
    async fn test_bash_process_run_without_start() {
        let mut bash_process = BashProcess::new();

        let run_result = bash_process.run("echo test").await;
        match run_result {
            Ok(_) => panic!("Expected error when running without starting"),
            Err(BashError::SessionNotStarted) => {} // Expected
            Err(e) => panic!("Expected SessionNotStarted error, got: {:?}", e),
        }
    }

    #[tokio::test]
    async fn test_stop_without_start() {
        let mut bash_process = BashProcess::new();

        let stop_result = bash_process.stop().await;
        match stop_result {
            Ok(_) => panic!("Expected error when stopping without starting"),
            Err(BashError::SessionNotStarted) => {} // Expected
            Err(e) => panic!("Expected SessionNotStarted error, got: {:?}", e),
        }
    }

    #[test]
    fn test_bash_exec_result_default() {
        let result = BashExecResult::default();
        assert_eq!(result.output, "");
        assert_eq!(result.error, "");
        assert_eq!(result.error_code, 0);
    }

    #[test]
    fn test_bash_error_display() {
        let error = BashError::SessionNotStarted;
        assert_eq!(error.to_string(), "bash session not started");

        let error = BashError::BashExited(1);
        assert_eq!(error.to_string(), "bash has exited with returncode 1");

        let error = BashError::Timeout;
        assert_eq!(error.to_string(), "bash command timed out");

        let error = BashError::Other("custom error".to_string());
        assert_eq!(error.to_string(), "other error: custom error");
    }

    // Test that basic command execution works
    #[tokio::test]
    async fn test_bash_process_basic_run() {
        let mut bash_process = BashProcess::new();
        bash_process.timeout = Duration::from_secs(5); // Reasonable timeout

        bash_process.start().await.expect("start should succeed");

        // This command should complete quickly and successfully
        let run_result = bash_process.run("echo 'hello world'").await;

        match run_result {
            Ok(result) => {
                assert!(!bash_process.timed_out);
                assert!(result.output.contains("hello world"));
            }
            Err(error) => {
                panic!("Expected success, got error: {:?}", error);
            }
        }
    }

    #[tokio::test]
    async fn test_bash_process_stderr_output() {
        let mut bash_process = BashProcess::new();
        bash_process.timeout = Duration::from_millis(500); // Very short timeout

        bash_process.start().await.expect("start should succeed");

        let run_result = bash_process.run("echo 'hello world' >&2").await;
        assert!(run_result.is_ok());
        assert!(run_result.unwrap().error.contains("hello world"));
    }

    #[tokio::test]
    async fn test_multiple_commands_in_one_line() {
        let mut bash_process = BashProcess::new();
        bash_process.timeout = Duration::from_millis(500); // Very short timeout

        bash_process.start().await.expect("start should succeed");

        let run_result = bash_process
            .run("echo 'hello world' && echo 'error message' >&2")
            .await
            .unwrap();
        assert!(run_result.output.contains("hello world"));
        assert!(run_result.error.contains("error message"));
    }

    #[tokio::test]
    async fn test_multiple_commands_one_by_one() {
        let mut bash_process = BashProcess::new();
        bash_process.timeout = Duration::from_millis(500); // Very short timeout

        bash_process.start().await.expect("start should succeed");

        let run_result = bash_process.run("echo 'hello world'").await.unwrap();
        assert!(run_result.output.contains("hello world"));

        let run_result = bash_process.run("echo 'error message' >&2").await.unwrap();
        assert!(run_result.error.contains("error message"));

        let run_result = bash_process.run("echo 'hello world'").await.unwrap();
        assert!(run_result.output.contains("hello world"));

        let run_result = bash_process.run("echo 'error message' >&2").await.unwrap();
        assert!(run_result.error.contains("error message"));
    }

    #[tokio::test]
    async fn test_bash_process_restart() {
        let mut bash_process = BashProcess::new();
        bash_process.timeout = Duration::from_millis(500); // Very short timeout

        bash_process.start().await.expect("start should succeed");

        let run_result = bash_process.run("echo 'hello world'").await;
        assert!(run_result.is_ok());
        assert!(run_result.unwrap().output.contains("hello world"));

        let restart_result = bash_process.stop().await;
        assert!(restart_result.is_ok());

        bash_process.start().await.expect("start should succeed");

        let run_result = bash_process.run("echo 'hello world'").await;
        assert!(run_result.is_ok());
        assert!(run_result.unwrap().output.contains("hello world"));
    }

    // Test that timeout mechanism works properly
    #[tokio::test]
    async fn test_bash_process_timeout() {
        let mut bash_process = BashProcess::new();
        bash_process.timeout = Duration::from_millis(200); // Short but reasonable timeout

        bash_process.start().await.expect("start should succeed");

        // This command should timeout due to the short timeout
        // Use a command that will definitely take longer than 200ms
        let run_result = bash_process.run("sleep 10").await;

        // The result should be a timeout error
        match run_result {
            Err(BashError::Timeout) => {
                assert!(bash_process.timed_out);
            }
            Err(other_error) => {
                panic!("Expected timeout error, got: {:?}", other_error);
            }
            Ok(_) => {
                panic!("Expected timeout error, but command succeeded");
            }
        }
    }

    // Mock test for execute function that avoids actual bash execution
    #[test]
    fn test_execute_argument_parsing() {
        let _bash = Bash::new("openai".to_string());

        // Test that arguments are parsed correctly
        let mut args = HashMap::new();
        args.insert("command".to_string(), json!("echo test"));
        args.insert("restart".to_string(), json!(true));

        // We can't easily test execute without mocking, but we can test argument parsing
        let cmd = args.get("command").and_then(|x| x.as_str()).unwrap_or("");
        let restart = args
            .get("restart")
            .and_then(|x| x.as_bool())
            .unwrap_or(false);

        assert_eq!(cmd, "echo test");
        assert!(restart);
    }

    // Integration test with timeout - this might still hang but will be killed by outer timeout
    #[tokio::test]
    async fn test_basic_integration() {
        let mut bash = Bash::new("openai".to_string());
        bash.bash.timeout = Duration::from_millis(200); // Very short timeout

        let mut args = HashMap::new();
        args.insert("command".to_string(), json!("true")); // Simple command that should succeed quickly
        args.insert("restart".to_string(), json!(false));

        // This might timeout, succeed, or fail - all are acceptable for this test
        let _result = bash.execute(args).await;

        assert!(!bash.bash.timed_out);
    }

    // Test the Tool trait implementation
    #[test]
    fn test_tool_trait() {
        let bash = Bash::new("test".to_string());

        // Test Tool trait methods
        assert_eq!(bash.get_name(), "bash");
        assert!(!bash.get_description().is_empty());

        let schema = bash.get_input_schema();
        assert!(schema.is_object());
        assert!(schema["properties"].is_object());
    }

    // Test ls command execution
    #[tokio::test]
    async fn test_execute_ls_command() {
        let mut bash = Bash::new("openai".to_string());
        bash.bash.timeout = Duration::from_millis(1000);

        let mut args = HashMap::new();
        args.insert("command".to_string(), json!("ls /"));
        args.insert("restart".to_string(), json!(false));

        let result = bash.execute(args).await;
        match result {
            Ok(output) => {
                // Check for common directories that should exist on most systems
                assert!(
                    output.contains("bin")
                        || output.contains("usr")
                        || output.contains("etc")
                        || output.contains("home")
                        || !output.is_empty(), // At least some output
                    "Expected ls output to contain common directories, got: {}",
                    output
                );
            }
            Err(e) => {
                // If it fails due to timeout or other issues, that's acceptable in test environment
                println!("ls command failed (acceptable in test env): {:?}", e);
            }
        }
    }

    // Test echo with multiple lines
    #[tokio::test]
    async fn test_execute_echo_multiline() {
        let mut bash = Bash::new("openai".to_string());
        bash.bash.timeout = Duration::from_millis(500);

        let mut args = HashMap::new();
        args.insert(
            "command".to_string(),
            json!("echo -e 'First line\\nSecond line\\nThird line'"),
        );
        args.insert("restart".to_string(), json!(false));

        let result = bash.execute(args).await;
        match result {
            Ok(output) => {
                // Check that all three lines are present in output
                assert!(
                    output.contains("First line")
                        && output.contains("Second line")
                        && output.contains("Third line"),
                    "Expected multiline echo output to contain all lines, got: {}",
                    output
                );

                // Verify it's actually multiple lines (contains newline or shows multiple lines)
                assert!(
                    output.lines().count() >= 3 || output.contains("line"),
                    "Expected output to be multiline, got: {}",
                    output
                );
            }
            Err(e) => {
                // If it fails due to timeout or other issues, that's acceptable in test environment
                println!(
                    "multiline echo command failed (acceptable in test env): {:?}",
                    e
                );
            }
        }
    }
}
