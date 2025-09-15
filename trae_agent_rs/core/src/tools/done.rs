// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

// task done tool

use crate::Tool;

#[derive(Default)]
pub struct TaskDone{}

impl Tool for  TaskDone{
    fn get_name(&self) -> &str {
        "task_done"
    }    

    fn reset(&mut self) {
    }

    fn execute(
            &mut self,
            arguments: std::collections::HashMap<String, serde_json::Value>,
        ) -> std::pin::Pin<Box<dyn Future<Output = Result<String, String>> + Send + '_>> {
            Box::pin(async move {
                Ok("Task done.".to_string())
            })
    }

    fn get_description(&self) -> &str {
        "Report the completion of the task. Note that you cannot call this tool before any verification is done. You can write reproduce / test script to verify your solution."    }

    fn get_input_schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type":"object",
            "properties":{
                "done":{"type":"bool",
                "description":"If the task is finished return true. If the task is not finished return falase"}
            },
            "required":["done"]
        })
    }
}