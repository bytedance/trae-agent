// the implementation of trae agent

use std::collections::HashMap;
use std::time::SystemTime;
use std::vec;

use tokio::sync::mpsc;

use crate::agent::base_agent::*;
use crate::llm_basics::{LLMUsage, TextContent};
use crate::trajectory::Recorder;
use crate::utils::trajectory::{LLMRecord, Trajectory, system_time_to_string};
use crate::{ContentItem, LLMMessage, Tool, agent};
use crate::{
    bash::Bash, edit_file::EditFile, read_file::ReadFile, read_many_files::ReadManyFiles,
    todo_list::TodoList, tools::list_directory::ListDirectory, write_file::WriteFile,
};

const TRAE_AGENT_TOOL_NAMES: [&str; 7] = [
    "str_replace_based_edit_tool",
    "bash",
    "list_directory",
    "read_file",
    "read_many_files",
    "todo_list",
    "write_file",
];

/// Messages that can be sent from TraeAgent to CLI for real-time updates
#[derive(Debug, Clone)]
pub enum AgentUpdate {
    /// Agent status changed (thinking, running tool, completed, etc.)
    StatusUpdate(String),
    /// Agent produced output text
    Output(String),
    /// Token usage information
    TokenUsage { input: u64, output: u64 },
    /// Agent step information
    StepUpdate { step: u32, description: String },
    /// Error occurred
    Error(String),
    /// Task completed successfully
    TaskCompleted(String),
}

pub struct TraeAgent {
    pub baseagent: agent::base_agent::BaseAgent,
    pub initial_msgs: Vec<LLMMessage>,

    pub trajectory_recorder: Trajectory,

    pub base_commit: Option<String>,
    pub must_patch: Option<String>,
    pub patch_path: Option<String>,

    /// Optional channel sender for real-time updates to CLI
    pub update_sender: Option<mpsc::UnboundedSender<AgentUpdate>>,
}

impl TraeAgent {
    pub fn new(base_agent: agent::base_agent::BaseAgent, path: Option<String>) -> Self {
        let default_path = {
            let timestamp = SystemTime::now()
                .duration_since(SystemTime::UNIX_EPOCH)
                .unwrap()
                .as_secs();
            format!("./trajectories/trajectory_{}.json", timestamp)
        };

        TraeAgent {
            baseagent: base_agent,
            initial_msgs: vec![],

            trajectory_recorder: Trajectory {
                path: path.unwrap_or(default_path),
                start_time: system_time_to_string(&SystemTime::now()),
                trajectory_data: None,
            },

            base_commit: None,
            must_patch: None,
            patch_path: None,
            update_sender: None,
        }
    }

    /// Set the update sender for real-time communication with CLI
    pub fn set_update_sender(&mut self, sender: mpsc::UnboundedSender<AgentUpdate>) {
        self.update_sender = Some(sender);
    }

    /// Send an update to the CLI if sender is available
    fn send_update(&self, update: AgentUpdate) {
        if let Some(sender) = &self.update_sender {
            let _ = sender.send(update);
        }
    }
}

impl Agent for TraeAgent {
    fn new_task(
        &mut self,
        task: String,
        args: Option<std::collections::HashMap<String, String>>,
        tool_names: Option<Vec<String>>,
    ) -> Result<(), AgentError> {
        self.baseagent.task = task;

        if tool_names.is_some() || tool_names.unwrap_or_default().is_empty() {
            let provider = &self.baseagent.model_config.model_provider;

            let mut tools_map: HashMap<String, usize> = HashMap::new();
            let mut tools: Vec<Box<dyn Tool>> = Vec::new();

            for tool in TRAE_AGENT_TOOL_NAMES {
                match tool {
                    "bash" => {
                        tools.push(Box::new(Bash::new(provider.name.clone())));

                        tools_map.insert(tool.to_string().clone(), tools.len() - 1);
                    }
                    "str_replace_based_edit_tool" => {
                        tools.push(Box::new(EditFile::default()));

                        tools_map.insert(tool.to_string().clone(), tools.len() - 1);
                    }
                    "list_directory" => {
                        tools.push(Box::new(ListDirectory::default()));

                        tools_map.insert(tool.to_string().clone(), tools.len() - 1);
                    }
                    "read_file" => {
                        tools.push(Box::new(ReadFile::default()));

                        tools_map.insert(tool.to_string().clone(), tools.len() - 1);
                    }
                    "read_many_files" => {
                        tools.push(Box::new(ReadManyFiles::default()));

                        tools_map.insert(tool.to_string().clone(), tools.len() - 1);
                    }
                    "todo_list" => {
                        tools.push(Box::new(TodoList::default()));

                        tools_map.insert(tool.to_string().clone(), tools.len() - 1);
                    }
                    "write_file" => {
                        tools.push(Box::new(WriteFile::default()));

                        tools_map.insert(tool.to_string().clone(), tools.len() - 1);
                    }
                    _ => {}
                }
            }

            self.baseagent.tools = tools;
            self.baseagent.tools_map = Some(tools_map);
        }

        // reset the init msg here
        self.initial_msgs = vec![];
        self.initial_msgs.push(LLMMessage {
            role: crate::MessageRole::System,
            content: Some(vec![ContentItem::Text(TextContent {
                text: TRAE_AGENT_SYSTEM_PROMPT.to_string(),
            })]),
            tool_call: None,
            tool_result: None,
        });

        let mut user_msg = String::new();
        if args.is_none() {
            return Err(AgentError::NoExtraArgument);
        }

        if args.as_ref().and_then(|m| m.get("project_path")).is_none() {
            return Err(AgentError::NoProjectPath);
        }

        if args.as_ref().and_then(|m| m.get("issue")).is_some() {
            let issue: String = args
                .as_ref()
                .and_then(|m| m.get("issue"))
                .map(|v| v.to_string())
                .unwrap_or_default();

            user_msg += &format!(
                "[Problem statement]: We're currently solving the following issue within our repository. \
            Here's the issue text:\n{}\n Your work directory is {} \n",
                issue,
                args.as_ref()
                    .and_then(|m| m.get("project_path").map(|s| s.as_str()))
                    .unwrap_or("")
            );
        };

        for attr in ["base_commit", "must_patch", "patch_path"] {
            if args.as_ref().and_then(|m| m.get(attr)).is_none() {
                let val: String = args
                    .as_ref()
                    .and_then(|m| m.get(attr))
                    .map(|v| v.to_string())
                    .unwrap_or_default();

                match attr {
                    "base_commit" => {
                        self.base_commit = Some(val);
                    }
                    "must_patch" => self.must_patch = Some(val),
                    "patch_path" => self.patch_path = Some(val),
                    _ => {}
                }
            }
        }

        self.initial_msgs.push(LLMMessage {
            role: crate::MessageRole::User,
            content: Some(vec![ContentItem::Text(TextContent { text: user_msg })]),
            tool_call: None,
            tool_result: None,
        });

        self.trajectory_recorder.start_recording(
            &self.baseagent.task,
            &self.baseagent.model_config.model_provider.name.to_string(),
            &self.baseagent.model_config.model.to_string(),
            self.baseagent.max_step.into(),
        );

        Ok(())
    }
    async fn run(&mut self) -> Result<AgentExecution, &'static str> {
        let start_time = SystemTime::now();

        // Send initial status update
        self.send_update(AgentUpdate::StatusUpdate(
            "Starting task execution".to_string(),
        ));
        self.send_update(AgentUpdate::Output(
            "🚀 Agent execution started".to_string(),
        ));

        //dbg!(&start_time);
        let mut exec_agent = AgentExecution {
            task: self.baseagent.task.clone(),
            steps: vec![],
            final_result: None,
            success: false,
            total_token: None,
            execution_time: 0.,
            agent_state: AgentState::IDLE,
        };

        let mut step_number = 1u32;
        // Set agent state to RUNNING when execution starts
        exec_agent.agent_state = AgentState::RUNNING;
        self.send_update(AgentUpdate::StatusUpdate("Running".to_string()));

        while step_number <= self.baseagent.max_step {
            // Send step update
            self.send_update(AgentUpdate::StepUpdate {
                step: step_number,
                description: format!("Executing step {}", step_number),
            });
            self.send_update(AgentUpdate::Output(format!(
                "🔄 Step {}: Starting execution",
                step_number
            )));

            // start a new step record
            let mut new_llm_record = LLMRecord {
                step_number,
                timestamp: SystemTime::now()
                    .duration_since(SystemTime::UNIX_EPOCH)
                    .unwrap()
                    .as_secs_f64()
                    .to_string(),
                request_content: format!("Step {}: Executing agent step", step_number),
                response_content: String::new(),
                tool_calls: vec![],
                error_message: None,
                token_usage: None,
                model: Some(self.baseagent.model_config.model.to_string()),
                provider: Some(self.baseagent.model_config.model_provider.name.to_string()),
                llmdetails: None,
                steps: None,
            };

            let mut step = AgentStep::new(step_number, AgentStepState::THINKING);
            self.send_update(AgentUpdate::StatusUpdate("Thinking".to_string()));

            let step_start_time = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_secs_f64();

            let exec_msg = self
                .baseagent
                .execute_step(&mut step, &self.initial_msgs, &mut exec_agent, None)
                .await;

            let step_end_time = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_secs_f64();

            let _step_execution_time = step_end_time - step_start_time;

            // update the record
            match exec_msg {
                Err(e) => {
                    // Handle error case
                    exec_agent.agent_state = AgentState::ERROR;
                    step.state = AgentStepState::ERROR;
                    step.error = Some(e.to_string());

                    let error_msg = format!("❌ Error in step {}: {}", step_number, e);
                    self.send_update(AgentUpdate::Error(error_msg.clone()));
                    self.send_update(AgentUpdate::Output(error_msg));

                    new_llm_record.response_content = format!("Error: {}", e);
                    new_llm_record.error_message = Some(e.to_string());
                    new_llm_record.steps = Some(step.clone());

                    self.trajectory_recorder.add_llm_record(new_llm_record);
                    self.trajectory_recorder.increment_error_count();

                    self.baseagent.finalize_step(
                        &mut step,
                        &mut self.initial_msgs,
                        &mut exec_agent,
                    );
                    break;
                }
                Ok(new_messages) => {
                    // Add new messages from the execution to our message history
                    self.initial_msgs.extend(new_messages.clone());

                    let success_msg = format!("✅ Step {} completed successfully", step_number);
                    self.send_update(AgentUpdate::Output(success_msg));

                    // Send token usage update if available
                    // TODO: Extract actual token usage from step execution
                    self.send_update(AgentUpdate::TokenUsage {
                        input: 100, // Placeholder - should be extracted from actual execution
                        output: 50, // Placeholder - should be extracted from actual execution
                    });

                    new_llm_record.response_content =
                        format!("Step completed with {} new messages", new_messages.len());
                    new_llm_record.steps = Some(step.clone());

                    self.trajectory_recorder.add_llm_record(new_llm_record);

                    self.baseagent.finalize_step(
                        &mut step,
                        &mut self.initial_msgs,
                        &mut exec_agent,
                    );

                    // Check if task is completed
                    if exec_agent.agent_state == AgentState::COMPLETED {
                        self.send_update(AgentUpdate::StatusUpdate("Completed".to_string()));
                        self.send_update(AgentUpdate::TaskCompleted(
                            "Task completed successfully".to_string(),
                        ));
                        break;
                    }
                }
            }

            step_number += 1;
        }

        // Check if we exceeded max steps without completion
        if step_number > self.baseagent.max_step && exec_agent.agent_state != AgentState::COMPLETED
        {
            let timeout_msg =
                "⏰ Task execution exceeded maximum steps without completion".to_string();
            exec_agent.final_result = Some(timeout_msg.clone());
            exec_agent.agent_state = AgentState::ERROR;
            exec_agent.success = false;

            self.send_update(AgentUpdate::Error(timeout_msg.clone()));
            self.send_update(AgentUpdate::Output(timeout_msg));
        } else if exec_agent.agent_state == AgentState::COMPLETED {
            exec_agent.success = true;
            self.send_update(AgentUpdate::Output(
                "🎉 Task execution completed successfully!".to_string(),
            ));
        }

        // Calculate execution time
        let dur = SystemTime::now()
            .duration_since(start_time)
            .expect("system clock went backwards");
        exec_agent.execution_time = dur.as_secs_f64();

        // Send final execution time update
        self.send_update(AgentUpdate::Output(format!(
            "⏱️ Total execution time: {:.2}s",
            exec_agent.execution_time
        )));

        // Collect total token usage from all steps
        exec_agent.total_token = Some(LLMUsage {
            input_tokens: 0,
            output_tokens: 0,
            cache_creation_input_tokens: 0,
            reasoning_tokens: 0,
            cache_read_input_tokens: 0,
        }); //TODO full implementation of total token

        // Finalize trajectory recording with execution results
        self.trajectory_recorder.finalize_recording(
            exec_agent.success,
            exec_agent.final_result.clone(),
            exec_agent.execution_time,
        );

        // Close tools implementation
        self.baseagent.close_tools();

        let _ = self.trajectory_recorder.save_record();

        Ok(exec_agent)
    }

    fn run_cli(_sender: mpsc::UnboundedSender<String>) {
        // This method is required by the trait but not used in our implementation
        // We use the set_update_sender method instead for channel communication
    }
}

pub const TRAE_AGENT_SYSTEM_PROMPT: &str = r###"You are an expert AI software engineering agent.

File Path Rule: All tools that take a `file_path` as an argument require an **absolute path**. You MUST construct the full, absolute path by combining the `[Project root path]` provided in the user's message with the file's path inside the project.

For example, if the project root is `/home/user/my_project` and you need to edit `src/main.py`, the correct `file_path` argument is `/home/user/my_project/src/main.py`. Do NOT use relative paths like `src/main.py`.

Your primary goal is to resolve a given GitHub issue by navigating the provided codebase, identifying the root cause of the bug, implementing a robust fix, and ensuring your changes are safe and well-tested.

Follow these steps methodically:

1.  Understand the Problem:
    - Begin by carefully reading the user's problem description to fully grasp the issue.
    - Identify the core components and expected behavior.

2.  Explore and Locate:
    - Use the available tools to explore the codebase.
    - Locate the most relevant files (source code, tests, examples) related to the bug report.

3.  Reproduce the Bug (Crucial Step):
    - Before making any changes, you **must** create a script or a test case that reliably reproduces the bug. This will be your baseline for verification.
    - Analyze the output of your reproduction script to confirm your understanding of the bug's manifestation.

4.  Debug and Diagnose:
    - Inspect the relevant code sections you identified.
    - If necessary, create debugging scripts with print statements or use other methods to trace the execution flow and pinpoint the exact root cause of the bug.

5.  Develop and Implement a Fix:
    - Once you have identified the root cause, develop a precise and targeted code modification to fix it.
    - Use the provided file editing tools to apply your patch. Aim for minimal, clean changes.

6.  Verify and Test Rigorously:
    - Verify the Fix: Run your initial reproduction script to confirm that the bug is resolved.
    - Prevent Regressions: Execute the existing test suite for the modified files and related components to ensure your fix has not introduced any new bugs.
    - Write New Tests: Create new, specific test cases (e.g., using `pytest`) that cover the original bug scenario. This is essential to prevent the bug from recurring in the future. Add these tests to the codebase.
    - Consider Edge Cases: Think about and test potential edge cases related to your changes.

7.  Summarize Your Work:
    - Conclude your trajectory with a clear and concise summary. Explain the nature of the bug, the logic of your fix, and the steps you took to verify its correctness and safety.

**Guiding Principle:** Act like a senior software engineer. Prioritize correctness, safety, and high-quality, test-driven development.

# GUIDE FOR HOW TO USE "sequential_thinking" TOOL:
- Your thinking should be thorough and so it's fine if it's very long. Set total_thoughts to at least 5, but setting it up to 25 is fine as well. You'll need more total thoughts when you are considering multiple possible solutions or root causes for an issue.
- Use this tool as much as you find necessary to improve the quality of your answers.
- You can run bash commands (like tests, a reproduction script, or 'grep'/'find' to find relevant context) in between thoughts.
- The sequential_thinking tool can help you break down complex problems, analyze issues step-by-step, and ensure a thorough approach to problem-solving.
- Don't hesitate to use it multiple times throughout your thought process to enhance the depth and accuracy of your solutions.

If you are sure the issue has been solved, you should call the `task_done` to finish the task.
"###;
