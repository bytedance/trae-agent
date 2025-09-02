// bash tool

use std::io::{self, BufReader};
use std::time::Duration;

use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufStream , BufWriter};
use tokio::process::{Child, ChildStdin, ChildStdout, Command};

use thiserror::Error;
use serde_json::Value;

use std::process::Stdio;

use crate::Tool;

pub struct Bash{
    model_provider: String,
}

impl Tool for Bash{
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

        let v: Value =serde_json::from_str(data).unwrap(); // since it is fixed so theoritically is should always be the same
        v
    }

    async fn execute(&self, arguments: std::collections::HashMap<String, serde_json::Value>) -> std::pin::Pin<Box<dyn Future<Output = Result<String, String>> + Send + '_>> {
        todo!()
    }
}


// set the bash process to be private field
struct bashprocess {
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


impl bashprocess{
    async fn start(&mut self)-> Result<(), BashError>{
        if self.started{
            return Ok(())
        }

        #[cfg(target_os="macos")]
        let mut cmd = Command::new("/bin/bash");

        //TODO: add other operating system

        #[cfg(target_os="macos")]
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

    async fn stop(&self){}

    async fn run(&self, command:&str)->Result<ToolExecResult,BashError>
    {


        todo!()
    }

    fn new()->Self{
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
pub enum BashError {
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

#[derive(Debug)]
pub struct ToolExecResult {
    pub output: String,
    pub error: String,
    pub error_code: i32,
}