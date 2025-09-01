// bash tool

use serde_json::Value;

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

    fn execute(&self, arguments: std::collections::HashMap<String, serde_json::Value>) -> std::pin::Pin<Box<dyn Future<Output = Result<String, String>> + Send + '_>> {
        todo!()
    }

}