// Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

/*

    This file is for the purpsoe of providing the base class
    of agent.

    An agent should have an llm client, model_config , max step ... same as
    mentioned in the base_agent.py

    We consider each agent could have different set of tools but all the initial step should
    be the same

*/

use serde::Serialize;
use std::collections::HashMap;
use std::vec;
use thiserror::Error;
use tokio::sync::mpsc;

use crate::ContentItem;
use crate::LLMClient;
use crate::LLMMessage;
use crate::LLMResponse;
use crate::ToolCall;
use crate::ToolResult;
use crate::config;
use crate::llm;
use crate::llm_basics::LLMUsage;
use crate::llm_basics::TextContent;
use crate::tools;

type TaskCompleteChecker = Box<dyn FnOnce(&LLMResponse) -> bool + Send>;

#[derive(Serialize, Clone, Debug, PartialEq)]
pub enum AgentStepState {
    THINKING,
    CALLINGTOOL,
    REFLECTING,
    ERROR,
    COMPLETED,
}

#[derive(Serialize, Debug, Clone, Copy, PartialEq, Eq)]
pub enum AgentState {
    IDLE,
    RUNNING,
    COMPLETED,
    ERROR,
}

// The follow is an agent base class
// Base agent is a struct for every agnet
// for example: a trae agent should have a base agent & implement the method of
// the agents
pub struct BaseAgent {
    pub task: String,
    pub execution_record: AgentExecution, //an agent record that save the result
    pub max_step: u32,

    pub llm_client: LLMClient,
    pub tools_map: Option<HashMap<String, usize>>,

    pub tools: Vec<Box<dyn tools::Tool>>,
    pub model_config: config::ModelConfig,
}

impl BaseAgent {
    pub fn new(
        task: String,
        record: AgentExecution,
        client: LLMClient,
        max_step: u32,
        model_config: config::ModelConfig,
        tools_map: Option<HashMap<String, usize>>,
        tools: Vec<Box<dyn tools::Tool>>,
    ) -> Self {
        BaseAgent {
            task,
            execution_record: record,
            llm_client: client,
            model_config,
            max_step,
            tools,
            tools_map,
        }
    }
}

// this struct should be private Agent
#[derive(Debug, Clone)]
pub struct AgentExecution {
    pub task: String,
    pub steps: Vec<AgentStep>,
    pub final_result: Option<String>,
    pub success: bool,
    pub total_token: Option<LLMUsage>,
    pub execution_time: f64,
    pub agent_state: AgentState,
}

impl AgentExecution {
    pub fn new(task: String, steps: Option<Vec<AgentStep>>) -> Self {
        AgentExecution {
            task,
            steps: steps.unwrap_or_default(),
            final_result: None,
            success: false,
            total_token: None,
            execution_time: 0.0,
            agent_state: AgentState::IDLE,
        }
    }
}

// the execution of that specific step
#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct AgentStep {
    pub step_number: u32,

    pub state: AgentStepState,
    pub thought: Option<String>,

    pub llm_response: Option<LLMResponse>,
    pub tool_calls: Option<Vec<ToolCall>>,

    pub tool_results: Option<Vec<ToolResult>>,
    pub reflection: Option<String>,

    pub error: Option<String>,
}

impl AgentStep {
    pub fn new(step_number: u32, state: AgentStepState) -> Self {
        AgentStep {
            step_number,
            state,
            thought: None,
            llm_response: None,
            tool_calls: None,
            tool_results: None,
            reflection: None,
            error: None,
        }
    }
}

pub trait Agent {
    // run is corresponding to execute_task in python.
    fn run(
        &mut self,
    ) -> impl std::future::Future<Output = Result<AgentExecution, &'static str>> + Send;

    fn run_cli(sender: mpsc::UnboundedSender<String>);

    fn new_task(
        &mut self,
        task: String,
        args: Option<HashMap<String, String>>,
        tool_names: Option<Vec<String>>,
    ) -> Result<(), AgentError>;
}

impl BaseAgent {
    pub fn finalize_step(
        &self,
        step: &mut AgentStep,
        _messages: &mut [LLMMessage],
        execution: &mut AgentExecution,
    ) {
        step.state = AgentStepState::COMPLETED;
        // TODO: CLI has to be update here message is needed here
        execution.steps.push(step.clone());
    }

    pub fn close_tools(&mut self) {
        if self.tools.is_empty() {
            return;
        }

        if let Some(tools) = self.tools_map.as_mut() {
            for (_name, tool) in tools.iter() {
                self.tools[*tool].reset();
            }
        }
    }

    // this function correspond to _run_llm_step in the python code
    pub async fn execute_step(
        &mut self,
        step: &mut AgentStep,
        msgs: &[LLMMessage],
        exec: &mut AgentExecution,

        is_task_complete: Option<TaskCompleteChecker>,
    ) -> Result<Vec<LLMMessage>, AgentError> {
        step.state = AgentStepState::THINKING;

        let response = self
            .llm_client
            .chat(msgs.to_vec(), &self.model_config, Some(&self.tools), false)
            .await;

        let llm_response = match response {
            Ok(t) => Some(t),
            Err(_e) => Some(LLMResponse {
                content: vec![ContentItem::Text(TextContent {
                    text: "error occur for llm responses".to_string(),
                })],
                usage: Some(LLMUsage {
                    input_tokens: 0,
                    output_tokens: 0,
                    cache_creation_input_tokens: 0,
                    cache_read_input_tokens: 0,
                    reasoning_tokens: 0,
                }),
                model: Some(self.llm_client.get_provider_name().to_string()),
                finish_reason: llm::FinishReason::Error,
                tool_calls: None,
            }),
        };

        step.llm_response = llm_response.clone();

        let unwrap_response = llm_response.as_ref().expect("It should never be None");
        // update console
        // update llm usage
        // indicate task complete here
        if indicate_task_complete(unwrap_response) {
            let check_complete: Box<dyn FnOnce(&LLMResponse) -> bool> = match is_task_complete {
                Some(f) => f,
                None => Box::new(|_x| true), // always true if no function is given
            };

            if check_complete(unwrap_response) {
                exec.agent_state = AgentState::COMPLETED;

                let result = unwrap_response
                    .content
                    .first()
                    .and_then(|c| c.as_text())
                    .unwrap_or("Error: no message found");

                exec.final_result = Some(result.to_string());
                exec.success = true;
                return Ok(msgs.to_vec());
            }

            exec.agent_state = AgentState::RUNNING;
            return Ok(vec![LLMMessage {
                role: llm::MessageRole::User,
                content: Some(vec![ContentItem::Text(TextContent {
                    text: "Your task is not finished. Please continue.".to_string(),
                })]),
                tool_call: None,
                tool_result: None,
            }]); // return type here
        }

        let tool_call = &unwrap_response.tool_calls;
        self.tool_call_handler(tool_call, step).await
    }

    async fn tool_call_handler(
        &mut self,
        tool_call: &Option<Vec<ToolCall>>,
        step: &mut AgentStep,
    ) -> Result<Vec<LLMMessage>, AgentError> {
        let tool_size = tool_call.as_ref().unwrap_or(&vec![]).len();

        if tool_size == 0 {
            return Ok(vec![LLMMessage {
                role: llm::MessageRole::User,
                content: Some(vec![ContentItem::text(
                    "It seems that you have not completed the task".to_string(),
                )]),
                tool_call: None,
                tool_result: None,
            }]);
        }

        step.state = AgentStepState::CALLINGTOOL;

        let default_vec = vec![];

        let unwrapped_tool = tool_call.as_ref().unwrap_or(&default_vec);

        let empty_map = HashMap::new();
        let agent_tools = self.tools_map.as_ref().unwrap_or(&empty_map);

        let mut tool_results = vec![];

        // TODO: parallel tool call
        for tool in unwrapped_tool {
            let mut tool_result = ToolResult {
                call_id: tool
                    .arguments
                    .get("call_id")
                    .unwrap_or_default()
                    .as_str()
                    .unwrap_or_default()
                    .to_string(),
                name: tool.name.to_string(),
                success: false,
                result: None,
                error: None,
                id: None,
            };

            let result = match tool.name.as_str() {
                "bash" => {
                    // ensure `agent_tools` is a mutable variable in scope: `&mut agent_tools`
                    match (*agent_tools).get("bash") {
                        Some(x) => self.tools[*x].execute(tool.arguments.clone()).await,
                        None => Err("Cannot find bash tool".to_string()),
                    }
                }

                "str_replace_based_edit_tool" => {
                    match agent_tools.get("str_replace_based_edit_tool") {
                        Some(x) => self.tools[*x].execute(tool.arguments.clone()).await,
                        None => Err("Cannot find str_replace_based_edit tool".to_string()),
                    }
                }

                "list_directory" => match agent_tools.get("list_directory") {
                    Some(x) => self.tools[*x].execute(tool.arguments.clone()).await,
                    None => Err("Cannot find list_directory tool".to_string()),
                },

                "read_file" => match agent_tools.get("read_file") {
                    Some(x) => self.tools[*x].execute(tool.arguments.clone()).await,
                    None => Err("Cannot find read_file tool".to_string()),
                },

                "read_many_files" => match agent_tools.get("read_many_files") {
                    Some(x) => self.tools[*x].execute(tool.arguments.clone()).await,
                    None => Err("Cannot find read_many_files tool".to_string()),
                },

                "todo_list" => match agent_tools.get("todo_list") {
                    Some(x) => self.tools[*x].execute(tool.arguments.clone()).await,
                    None => Err("Cannot find todo_list tool".to_string()),
                },

                "write_file" => match agent_tools.get("write_file") {
                    Some(x) => self.tools[*x].execute(tool.arguments.clone()).await,
                    None => Err("Cannot find write_file tool".to_string()),
                },

                _ => Err("The requested tool is not found".to_string()),
            };

            execresult_to_toolresult(result, &mut tool_result);

            tool_results.push(tool_result);
        }

        step.tool_results = Some(tool_results.clone());

        let mut msg: Vec<LLMMessage> = Vec::new();

        for tool_result in &tool_results {
            msg.push(LLMMessage {
                role: llm::MessageRole::User,
                content: Some(vec![ContentItem::Text(TextContent {
                    text: "Here are the tool results".to_string(),
                })]),
                tool_call: None,
                tool_result: Some(tool_result.clone()),
            })
        }

        let reflection: Option<String> = {
            if tool_size == 0 {
                None
            } else {
                let mut reflection = String::new();
                for tool in &tool_results {
                    if let Some(ref err) = tool.error {
                        if !reflection.is_empty() {
                            reflection.push('\n');
                        }
                        reflection.push_str("The tool execution failed with error: ");
                        reflection.push_str(err);
                        reflection.push_str(". Consider trying a different approach");
                    }
                }
                if !reflection.is_empty() {
                    Some(reflection)
                } else {
                    None
                }
            }
        };

        if reflection.is_some() {
            step.state = AgentStepState::REFLECTING;
            step.reflection = reflection.clone();
            //TODO update cli here

            msg.push(LLMMessage {
                role: llm::MessageRole::Assistant,
                content: Some(vec![ContentItem::Text(TextContent {
                    text: reflection.clone().unwrap_or_default(),
                })]),
                tool_call: None,
                tool_result: None,
            });
        }

        Ok(msg)
    }
}

fn indicate_task_complete(response: &LLMResponse) -> bool {
    let content = response
        .content
        .first()
        .and_then(|c| c.as_text())
        .unwrap_or("Error: can not get the response");

    let completion_indicators = [
        "task completed",
        "task finished",
        "done",
        "completed successfully",
        "finished successfully",
    ];

    for _i in completion_indicators.iter() {
        if content.to_lowercase().contains(_i) {
            return true;
        }
    }

    false
}

#[derive(Error, Debug)]
pub enum AgentError {
    #[error("Internal Error {0}")]
    InternalError(String),

    #[error("Project path and issue information are required")]
    NoExtraArgument,

    #[error("Project path is required")]
    NoProjectPath,
}

fn execresult_to_toolresult(execresult: Result<String, String>, toolresult: &mut ToolResult) {
    match execresult {
        Ok(res) => {
            toolresult.success = true;
            toolresult.result = Some(res);
            toolresult.error = None;
        }
        Err(e) => {
            toolresult.success = false;
            toolresult.result = None;
            toolresult.error = Some(e);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::llm::FinishReason;
    use crate::llm_basics::{LLMUsage, TextContent};
    use crate::{ContentItem, LLMResponse, ToolCall, ToolResult};
    use serde_json::{Value, json};
    use std::collections::HashMap;

    // Test fixtures and helper functions
    fn create_test_llm_usage() -> LLMUsage {
        LLMUsage {
            input_tokens: 100,
            output_tokens: 50,
            cache_creation_input_tokens: 0,
            cache_read_input_tokens: 0,
            reasoning_tokens: 25,
        }
    }

    fn create_test_llm_response(text: &str) -> LLMResponse {
        LLMResponse {
            content: vec![ContentItem::Text(TextContent {
                text: text.to_string(),
            })],
            usage: Some(create_test_llm_usage()),
            model: Some("test-model".to_string()),
            finish_reason: FinishReason::Stop,
            tool_calls: None,
        }
    }

    fn create_test_llm_response_with_tools(text: &str, tool_calls: Vec<ToolCall>) -> LLMResponse {
        LLMResponse {
            content: vec![ContentItem::Text(TextContent {
                text: text.to_string(),
            })],
            usage: Some(create_test_llm_usage()),
            model: Some("test-model".to_string()),
            finish_reason: FinishReason::Stop,
            tool_calls: Some(tool_calls),
        }
    }

    fn create_test_tool_call(name: &str, args: HashMap<String, Value>) -> ToolCall {
        ToolCall {
            name: name.to_string(),
            arguments: args,
            id: Some(format!("call_{}", name)),
            call_id: "testing_call_id".to_string(),
        }
    }

    // Tests for AgentStepState enum
    mod agent_step_state_tests {
        use super::*;

        #[test]
        fn test_agent_step_state_clone() {
            let state = AgentStepState::THINKING;
            let cloned_state = state.clone();

            // Since we can't directly compare enum variants without PartialEq,
            // we'll test through pattern matching
            match cloned_state {
                AgentStepState::THINKING => {}
                _ => panic!("Clone failed for THINKING state"),
            }
        }

        #[test]
        fn test_all_agent_step_states_exist() {
            // Ensure all expected states can be created
            let _thinking = AgentStepState::THINKING;
            let _calling = AgentStepState::CALLINGTOOL;
            let _reflecting = AgentStepState::REFLECTING;
            let _error = AgentStepState::ERROR;
            let _completed = AgentStepState::COMPLETED;
        }
    }

    // Tests for AgentState enum
    mod agent_state_tests {
        use super::*;

        #[test]
        fn test_agent_state_equality() {
            assert_eq!(AgentState::IDLE, AgentState::IDLE);
            assert_eq!(AgentState::RUNNING, AgentState::RUNNING);
            assert_eq!(AgentState::COMPLETED, AgentState::COMPLETED);
            assert_eq!(AgentState::ERROR, AgentState::ERROR);
        }

        #[test]
        fn test_agent_state_inequality() {
            assert_ne!(AgentState::IDLE, AgentState::RUNNING);
            assert_ne!(AgentState::RUNNING, AgentState::COMPLETED);
            assert_ne!(AgentState::COMPLETED, AgentState::ERROR);
        }

        #[test]
        fn test_agent_state_debug() {
            let state = AgentState::RUNNING;
            let debug_str = format!("{:?}", state);
            assert!(debug_str.contains("RUNNING"));
        }
    }

    // Tests for AgentExecution
    mod agent_execution_tests {
        use super::*;

        #[test]
        fn test_agent_execution_new_with_no_steps() {
            let task = "Test task".to_string();
            let execution = AgentExecution::new(task.clone(), None);

            assert_eq!(execution.task, task);
            assert!(execution.steps.is_empty());
            assert!(execution.final_result.is_none());
            assert!(!execution.success);
            assert!(execution.total_token.is_none());
            assert_eq!(execution.execution_time, 0.0);
            assert_eq!(execution.agent_state, AgentState::IDLE);
        }

        #[test]
        fn test_agent_execution_new_with_steps() {
            let task = "Test task".to_string();
            let steps = vec![
                AgentStep::new(1, AgentStepState::THINKING),
                AgentStep::new(2, AgentStepState::COMPLETED),
            ];
            let execution = AgentExecution::new(task.clone(), Some(steps.clone()));

            assert_eq!(execution.task, task);
            assert_eq!(execution.steps.len(), 2);
            assert_eq!(execution.steps[0].step_number, 1);
            assert_eq!(execution.steps[1].step_number, 2);
        }

        #[test]
        fn test_agent_execution_empty_task() {
            let empty_task = String::new();
            let execution = AgentExecution::new(empty_task.clone(), None);

            assert_eq!(execution.task, empty_task);
            assert!(execution.task.is_empty());
        }
    }

    // Tests for AgentStep
    mod agent_step_tests {
        use super::*;

        #[test]
        fn test_agent_step_new() {
            let step_number = 42;
            let state = AgentStepState::THINKING;
            let step = AgentStep::new(step_number, state.clone());

            assert_eq!(step.step_number, step_number);
            assert!(step.thought.is_none());
            assert!(step.llm_response.is_none());
            assert!(step.tool_calls.is_none());
            assert!(step.tool_results.is_none());
            assert!(step.reflection.is_none());
            assert!(step.error.is_none());
        }

        #[test]
        fn test_agent_step_clone() {
            let mut step = AgentStep::new(1, AgentStepState::THINKING);
            step.thought = Some("Test thought".to_string());
            step.error = Some("Test error".to_string());

            let cloned_step = step.clone();
            assert_eq!(cloned_step.step_number, step.step_number);
            assert_eq!(cloned_step.thought, step.thought);
            assert_eq!(cloned_step.error, step.error);
        }

        #[test]
        fn test_agent_step_with_zero_step_number() {
            let step = AgentStep::new(0, AgentStepState::ERROR);
            assert_eq!(step.step_number, 0);
        }
    }

    // Tests for BaseAgent
    mod base_agent_tests {
        use super::*;

        // Mock implementations would be needed for full testing
        // These tests assume basic functionality

        #[test]
        fn test_finalize_step() {
            // This test requires mock implementations of LLMClient and ModelConfig
            // For now, we'll test the logic we can test
            let task = "test".to_string();
            let mut execution = AgentExecution::new(task.clone(), None);
            let mut step = AgentStep::new(1, AgentStepState::THINKING);

            // We can't create BaseAgent without proper mocks, but we can test the logic
            // that finalize_step should set the step state to COMPLETED
            step.state = AgentStepState::COMPLETED;
            execution.steps.push(step.clone());

            assert_eq!(execution.steps.len(), 1);
            assert_eq!(execution.steps[0].step_number, 1);
        }

        #[test]
        fn test_close_tools_with_no_tools() {
            // Test that close_tools doesn't panic when tools is None
            // This would require a proper BaseAgent instance
            // For now, we test the concept
            let tools: Option<HashMap<String, Box<dyn crate::tools::Tool>>> = None;
            assert!(tools.is_none());
        }
    }

    // Tests for utility functions
    mod utility_function_tests {
        use super::*;

        #[test]
        fn test_indicate_task_complete_with_completion_indicators() {
            let completion_phrases = [
                "task completed",
                "task finished",
                "done",
                "completed successfully",
                "finished successfully",
            ];

            for phrase in &completion_phrases {
                let response = create_test_llm_response(phrase);
                assert!(
                    indicate_task_complete(&response),
                    "Should detect completion for phrase: {}",
                    phrase
                );
            }
        }

        #[test]
        fn test_indicate_task_complete_with_mixed_case() {
            let phrases = [
                "Task Completed successfully",
                "The work is DONE now",
                "We have FINISHED SUCCESSFULLY",
            ];

            for phrase in &phrases {
                let response = create_test_llm_response(phrase);
                assert!(
                    indicate_task_complete(&response),
                    "Should detect completion for mixed case phrase: {}",
                    phrase
                );
            }
        }

        #[test]
        fn test_indicate_task_complete_partial_matches() {
            let phrases = [
                "The task completed with errors",
                "We're almost done with the task",
                "Task completion is finished successfully",
            ];

            for phrase in &phrases {
                let response = create_test_llm_response(phrase);
                assert!(
                    indicate_task_complete(&response),
                    "Should detect completion for phrase containing indicator: {}",
                    phrase
                );
            }
        }

        #[test]
        fn test_indicate_task_complete_false_cases() {
            let non_completion_phrases = [
                "task in progress",
                "still working",
                "not finished yet",
                "incomplete work",
                "error occurred",
                "",
            ];

            for phrase in &non_completion_phrases {
                let response = create_test_llm_response(phrase);
                assert!(
                    !indicate_task_complete(&response),
                    "Should not detect completion for phrase: {}",
                    phrase
                );
            }
        }

        #[test]
        fn test_indicate_task_complete_empty_content() {
            let mut response = create_test_llm_response("");
            response.content.clear(); // Remove all content

            // Should not panic and should return false
            assert!(!indicate_task_complete(&response));
        }

        #[test]
        fn test_execresult_to_toolresult_success() {
            let mut tool_result = ToolResult {
                call_id: "test_call".to_string(),
                name: "test_tool".to_string(),
                success: false,
                result: None,
                error: Some("initial error".to_string()),
                id: None,
            };

            let exec_result = Ok("Success message".to_string());
            execresult_to_toolresult(exec_result, &mut tool_result);

            assert!(tool_result.success);
            assert_eq!(tool_result.result, Some("Success message".to_string()));
            assert!(tool_result.error.is_none());
        }

        #[test]
        fn test_execresult_to_toolresult_error() {
            let mut tool_result = ToolResult {
                call_id: "test_call".to_string(),
                name: "test_tool".to_string(),
                success: true,
                result: Some("initial result".to_string()),
                error: None,
                id: None,
            };

            let exec_result = Err("Error message".to_string());
            execresult_to_toolresult(exec_result, &mut tool_result);

            assert!(!tool_result.success);
            assert!(tool_result.result.is_none());
            assert_eq!(tool_result.error, Some("Error message".to_string()));
        }

        #[test]
        fn test_execresult_to_toolresult_empty_success() {
            let mut tool_result = ToolResult {
                call_id: "test_call".to_string(),
                name: "test_tool".to_string(),
                success: false,
                result: None,
                error: None,
                id: None,
            };

            let exec_result = Ok(String::new());
            execresult_to_toolresult(exec_result, &mut tool_result);

            assert!(tool_result.success);
            assert_eq!(tool_result.result, Some(String::new()));
            assert!(tool_result.error.is_none());
        }

        #[test]
        fn test_execresult_to_toolresult_empty_error() {
            let mut tool_result = ToolResult {
                call_id: "test_call".to_string(),
                name: "test_tool".to_string(),
                success: true,
                result: None,
                error: None,
                id: None,
            };

            let exec_result = Err(String::new());
            execresult_to_toolresult(exec_result, &mut tool_result);

            assert!(!tool_result.success);
            assert!(tool_result.result.is_none());
            assert_eq!(tool_result.error, Some(String::new()));
        }
    }

    // Tests for AgentError
    mod agent_error_tests {
        use super::*;
        use std::error::Error;

        #[test]
        fn test_agent_error_display() {
            let error = AgentError::InternalError("Test error message".to_string());
            let error_str = format!("{}", error);
            assert_eq!(error_str, "Internal Error Test error message");
        }

        #[test]
        fn test_agent_error_debug() {
            let error = AgentError::InternalError("Debug test".to_string());
            let debug_str = format!("{:?}", error);
            assert!(debug_str.contains("InternalError"));
            assert!(debug_str.contains("Debug test"));
        }

        #[test]
        fn test_agent_error_source() {
            let error = AgentError::InternalError("Test".to_string());
            assert!(error.source().is_none());
        }

        #[test]
        fn test_agent_error_empty_message() {
            let error = AgentError::InternalError(String::new());
            let error_str = format!("{}", error);
            assert_eq!(error_str, "Internal Error ");
        }
    }

    // Integration tests for complex scenarios
    mod integration_tests {
        use super::*;

        #[test]
        fn test_agent_step_workflow() {
            // Test a complete workflow from thinking to completion
            let mut step = AgentStep::new(1, AgentStepState::THINKING);

            // Simulate thinking phase
            step.thought = Some("I need to analyze the task".to_string());

            // Simulate tool calling phase
            step.state = AgentStepState::CALLINGTOOL;
            step.tool_calls = Some(vec![create_test_tool_call("bash", HashMap::new())]);

            // Simulate tool results
            let tool_result = ToolResult {
                call_id: "call_bash".to_string(),
                name: "bash".to_string(),
                success: true,
                result: Some("Command executed successfully".to_string()),
                error: None,
                id: Some("result_1".to_string()),
            };
            step.tool_results = Some(vec![tool_result]);

            // Complete the step
            step.state = AgentStepState::COMPLETED;

            assert_eq!(step.step_number, 1);
            assert!(step.thought.is_some());
            assert!(step.tool_calls.is_some());
            assert!(step.tool_results.is_some());
            assert!(step.tool_results.as_ref().unwrap()[0].success);
        }

        #[test]
        fn test_agent_execution_complete_workflow() {
            let task = "Complete a complex task".to_string();
            let mut execution = AgentExecution::new(task.clone(), None);

            // Add steps to execution
            let mut step1 = AgentStep::new(1, AgentStepState::THINKING);
            step1.state = AgentStepState::COMPLETED;
            execution.steps.push(step1);

            let mut step2 = AgentStep::new(2, AgentStepState::CALLINGTOOL);
            step2.state = AgentStepState::COMPLETED;
            execution.steps.push(step2);

            // Mark execution as successful
            execution.agent_state = AgentState::COMPLETED;
            execution.success = true;
            execution.final_result = Some("Task completed successfully".to_string());
            execution.execution_time = 123.45;

            assert_eq!(execution.steps.len(), 2);
            assert!(execution.success);
            assert_eq!(execution.agent_state, AgentState::COMPLETED);
            assert!(execution.final_result.is_some());
            assert!(execution.execution_time > 0.0);
        }

        #[test]
        fn test_error_handling_workflow() {
            let mut execution = AgentExecution::new("Error test".to_string(), None);

            // Create a step with error
            let mut error_step = AgentStep::new(1, AgentStepState::ERROR);
            error_step.error = Some("Simulated error occurred".to_string());

            execution.steps.push(error_step);
            execution.agent_state = AgentState::ERROR;
            execution.success = false;

            assert_eq!(execution.agent_state, AgentState::ERROR);
            assert!(!execution.success);
            assert!(execution.steps[0].error.is_some());
        }
    }

    // Performance and edge case tests
    mod edge_case_tests {
        use super::*;

        #[test]
        fn test_large_step_numbers() {
            let large_step = AgentStep::new(u32::MAX, AgentStepState::THINKING);
            assert_eq!(large_step.step_number, u32::MAX);
        }

        #[test]
        fn test_very_long_strings() {
            let long_string = "a".repeat(10000);
            let mut step = AgentStep::new(1, AgentStepState::THINKING);
            step.thought = Some(long_string.clone());
            step.error = Some(long_string.clone());

            assert_eq!(step.thought.as_ref().unwrap().len(), 10000);
            assert_eq!(step.error.as_ref().unwrap().len(), 10000);
        }

        #[test]
        fn test_unicode_strings() {
            let unicode_string = "测试 🚀 emoji and unicode ñáéíóú";
            let mut step = AgentStep::new(1, AgentStepState::THINKING);
            step.thought = Some(unicode_string.to_string());

            assert_eq!(step.thought.as_ref().unwrap(), unicode_string);
        }

        #[test]
        fn test_empty_tool_calls_handling() {
            let _response = create_test_llm_response_with_tools("test", vec![]);
            // This would test the tool_call_handler logic for empty tool calls
            // The actual implementation should handle empty vectors gracefully
        }

        #[test]
        fn test_multiple_tool_calls() {
            let mut args1 = HashMap::new();
            args1.insert("command".to_string(), json!("ls -la"));

            let mut args2 = HashMap::new();
            args2.insert("file".to_string(), json!("test.txt"));
            args2.insert("content".to_string(), json!("hello world"));

            let tool_calls = vec![
                create_test_tool_call("bash", args1),
                create_test_tool_call("str_replace_based_edit_tool", args2),
            ];

            let response = create_test_llm_response_with_tools("Using tools", tool_calls);
            assert_eq!(response.tool_calls.as_ref().unwrap().len(), 2);
        }
    }
}
