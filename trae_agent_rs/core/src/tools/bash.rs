// bash tool

use std::f32::consts::E;
use std::fmt::format;
use std::io::{self, BufReader};
use std::time::Duration;

use tokio::io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufStream, BufWriter};
use tokio::process::{Child, ChildStdin, ChildStdout, Command};

use tokio::time;

use serde_json::Value;
use thiserror::Error;

use std::process::Stdio;

use crate::Tool;

pub struct Bash {
    model_provider: String,
    bash: BaseProcess,
}

impl Tool for Bash {
    fn get_name(&self) -> &str {
        "bash"
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

        let v: Value = serde_json::from_str(data).unwrap(); // since it is fixed so theoritically is should always be the same
        v
    }

    fn execute(
        &mut self,
        arguments: std::collections::HashMap<String, serde_json::Value>,
    ) -> std::pin::Pin<Box<dyn Future<Output = Result<String, String>> + Send + '_>> {
        
            Box::pin(async move {
                        let cmd = arguments.get("command")
                            .and_then(|x| x.as_str())
                            .unwrap_or("");

                        let restart = arguments.get("restart")
                            .and_then(|x| x.as_bool())
                            .unwrap_or(false);

                        // Assuming `self.bash.start()` is an asynchronous operation
                        let starterr = self.bash.start().await;


                        if let Err(e) = starterr{
                            return Err(format!("fail to start the bash {}", e.to_string()))
                        }
                        

                        // run the command 
                        let exec_result = self.bash.run(cmd).await;

                        if let Err(e) = exec_result{
                            return Err(format!("fail to execute command: {} , getting error: {}" ,cmd ,e));
                        }

                        if restart {
                            let restart_result = self.bash.stop().await;
                            
                            if let Err(e) = restart_result{
                                return Err(format!("retart fail error: {}" , e));
                            }

                            let rebot_result = self.bash.start().await;

                            if let Err(e) = rebot_result{
                                return Err(format!("rebot fail error: {}" , e));
                            }
                        }
                        
                        match exec_result{
                            Ok(res)=>{
                                if res.error != "" || res.error.len() != 0 || res.error_code != 0 {
                                    return Err(format!("Error: {} , Error code: {} " , res.error , res.error_code))    
                                }

                                return Ok(res.output);

                            },
                            Err(e) => {
                                return Err(format!("Unexpected Error {}" , e));// this should never happend due to previous check
                            }
                        }
                    })

    }
}


// set the bash process to be private field
struct BaseProcess {
    child: Option<Child>,
    stdin: Option<ChildStdin>,
    stdout: Option<ChildStdout>,
    // We do not capture stderr separately here, but can be extended.
    started: bool,
    timed_out: bool,
    timeout: Duration,
    output_delay: Duration,
    sentinel: String,
}

impl BaseProcess {
    async fn start(&mut self) -> Result<(), BashError> {
        if self.started {
            return Ok(());
        }

        #[cfg(target_os = "macos")]
        let mut cmd = Command::new("/bin/bash");

        //TODO: add other operating system

        #[cfg(target_os = "macos")]
        {
            cmd.stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped());
        }

        let mut child = cmd.spawn().map_err(BashError::Io)?;

        let stdin = child.stdin.take().ok_or(BashError::SessionNotStarted)?;
        let stdout = child.stdout.take().ok_or(BashError::SessionNotStarted)?;

        self.stdin = Some(stdin);
        self.stdout = Some(stdout);

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
            if let Some(_) = child.try_wait()? {
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
        if !self.started {
            return Err(BashError::SessionNotStarted);
        }

        //WARNING ALL REFERENCE ARE NOW MUTABLE !
        //CONCURRENT RUNNING IN SAME PROCESS IS NOT ALLOWED
        let child = self
            .child
            .as_mut()
            .ok_or_else(|| BashError::SessionNotStarted)?;
        let stdin = self
            .stdin
            .as_mut()
            .ok_or_else(|| BashError::Other("stdin not available".to_string()))?;
        let stdout = self.stdout.as_mut().ok_or(BashError::SessionNotStarted)?;

        if let Some(code) = child.try_wait()? {
            return Err(BashError::BashExited(code.code().unwrap_or(-1)));
        }

        if self.timed_out {
            return Err(BashError::Timeout);
        }

        let (sentinel_before, _, sentinel_after) = {
            let parts: Vec<_> = self.sentinel.split("__ERROR_CODE__").collect();
            (parts[0], "__ERROR_CODE__", parts[1])
        };

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

        stdin.write_all(full_command.as_bytes()).await?;
        stdin.flush().await?;

        let mut output_accum = String::new();
        let mut error_accum = String::new();
        let mut error_code: Option<i32> = None;

        // Timeout wrapper
        let timeout = self.timeout;
        let mut timed_out = false;
        let mut buffer = String::new();
        let stdout_reader = stdout;

        loop {
            buffer.clear();
            let read_fut = stdout_reader.read_to_string(&mut buffer);

            match time::timeout(timeout, read_fut).await {
                Ok(Ok(0)) => {
                    break;
                }
                Ok(Ok(_)) => {
                    // Check if sentinel is found
                    if buffer.contains(sentinel_before) {
                        if let Some(pos) = buffer.find(sentinel_before) {
                            output_accum.push_str(&buffer[..pos]);
                            let rest = &buffer[pos + sentinel_before.len()..];

                            if rest.len() > sentinel_after.len() {
                                if rest.ends_with(sentinel_after) {
                                    let code_str = &rest[..rest.len() - sentinel_after.len()];
                                    if let Ok(code) = code_str.trim().parse::<i32>() {
                                        error_code = Some(code);
                                    }
                                }
                            }
                        }

                        break;
                    } else {
                        // Accumulate output as normal
                        output_accum.push_str(&buffer);
                    }
                }
                Ok(Err(e)) => return Err(BashError::Io(e)),
                Err(_) => {
                    timed_out = true;
                    break;
                }
            }
        }

        if timed_out {
            self.timed_out = true;
            return Err(BashError::Timeout);
        }

        if let Some(child) = &mut self.child {
            if let Some(mut stderr) = child.stderr.take() {
                let mut err_buf = Vec::new();
                let _ = stderr.read_to_end(&mut err_buf).await;
                error_accum = String::from_utf8_lossy(&err_buf).to_string();
                // put stderr back (not strictly necessary here)
                child.stderr.replace(stderr);
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
