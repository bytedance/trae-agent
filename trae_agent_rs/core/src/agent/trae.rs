// the implementation of trae agent

use std::collections::HashMap;
use std::time::SystemTime;
use std::vec;

use crate::agent::base_agent::*;
use crate::bash::Bash;
use crate::edit::Edit;
use crate::llm_basics::{LLMUsage, TextContent};
use crate::trajectories::trajectories::{LLMRecord, Trajectory, system_time_to_string};
use crate::{ContentItem, LLMMessage, Tool, agent};

const TRAE_AGENT_TOOL_NAMES: [&str; 2] = ["str_replace_based_edit_tool", "bash"];

pub struct TraeAgent {
    pub baseagent: agent::base_agent::BaseAgent,
    pub initial_msgs: Vec<LLMMessage>,

    pub trajectory_recorder: Trajectory,

    pub base_commit: Option<String>,
    pub must_patch: Option<String>,
    pub patch_path: Option<String>,
}

impl TraeAgent {
    pub fn new(base_agent: agent::base_agent::BaseAgent, path: Option<String>) -> Self {
        TraeAgent {
            baseagent: base_agent,
            initial_msgs: vec![],

            trajectory_recorder: Trajectory {
                path: path.unwrap_or("./".to_string()),
                start_time: system_time_to_string(&SystemTime::now()),
                trajectory_data: None,
            },

            base_commit: None,
            must_patch: None,
            patch_path: None,
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

        if tool_names.is_some() || tool_names.unwrap_or(vec![]).len() == 0 {
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
                        tools.push(Box::new(Edit::new()));

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
        //    let mut messages = self.initial_msgs.clone(); // Work with a mutable copy of messages
        // Set agent state to RUNNING when execution starts
        exec_agent.agent_state = AgentState::RUNNING;

        while step_number <= self.baseagent.max_step {
            println!("Agent is running step: {}", &step_number);

            // start a new step record
            let mut new_llm_record = LLMRecord {
                content: "".to_string(),
                token_usage: None,
                model: Some(self.baseagent.model_config.model.to_string().clone()),
                provider: Some(
                    self.baseagent
                        .model_config
                        .model_provider
                        .name
                        .to_string()
                        .clone(),
                ),
                llmdetails: None,
                steps: None,
            };

            let mut step = AgentStep::new(step_number, AgentStepState::THINKING);

            let exec_msg = self
                .baseagent
                .execute_step(&mut step, &self.initial_msgs, &mut exec_agent, None)
                .await;

            // update the record

            match exec_msg {
                Err(e) => {
                    // Handle error case
                    exec_agent.agent_state = AgentState::ERROR;
                    step.state = AgentStepState::ERROR;
                    step.error = Some(e.to_string());

                    self.baseagent.finalize_step(
                        &mut step,
                        &mut self.initial_msgs,
                        &mut exec_agent,
                    );
                    break;
                }
                Ok(new_messages) => {
                    // Add new messages from the execution to our message history
                    self.initial_msgs.extend(new_messages);

                    self.baseagent.finalize_step(
                        &mut step,
                        &mut self.initial_msgs,
                        &mut exec_agent,
                    );

                    // Check if task is completed
                    if exec_agent.agent_state == AgentState::COMPLETED {
                        break;
                    }
                }
            }

            new_llm_record.steps = Some(step.clone());

            // save the record
            self.trajectory_recorder
                .trajectory_data
                .as_mut()
                .unwrap()
                .llm_interaction
                .push(new_llm_record);

            step_number += 1;
        }

        // Check if we exceeded max steps without completion
        if step_number > self.baseagent.max_step && exec_agent.agent_state != AgentState::COMPLETED
        {
            exec_agent.final_result =
                Some("Task execution exceeded maximum steps without completion".to_string());
            exec_agent.agent_state = AgentState::ERROR;
            exec_agent.success = false;
        } else if exec_agent.agent_state == AgentState::COMPLETED {
            exec_agent.success = true;
        }

        // Calculate execution time
        let dur = SystemTime::now()
            .duration_since(start_time)
            .expect("system clock went backwards");
        exec_agent.execution_time = dur.as_secs_f64();

        // Collect total token usage from all steps
        exec_agent.total_token = Some(LLMUsage {
            input_tokens: 0,
            output_tokens: 0,
            cache_creation_input_tokens: 0,
            reasoning_tokens: 0,
            cache_read_input_tokens: 0,
        }); //TODO full implementation of total token

        // TODO: refactor & extract it to another function
        self.trajectory_recorder
            .trajectory_data
            .as_mut()
            .unwrap()
            .execution_time = exec_agent.execution_time.clone();

        self.trajectory_recorder
            .trajectory_data
            .as_mut()
            .unwrap()
            .success = exec_agent.success;

        // Close tools implementation
        self.baseagent.close_tools();

        // TODO: update CLI here if needed
        // You might want to add CLI updates for final results
        // Update the initial_msgs with the final message state for potential future use

        Ok(exec_agent)
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
