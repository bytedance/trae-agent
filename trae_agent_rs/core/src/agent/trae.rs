// the implementation of trae agent

use core::task;
use std::time::{Duration, SystemTime};
use std::vec;

use crate::{agent, base, LLMMessage};
use crate::agent::base_agent::*;

const TraeAgentToolNames: [&str;5] = [
    "str_replace_based_edit_tool",
    "sequentialthinking",
    "json_edit_tool",
    "task_done",
    "bash",
];

pub struct TraeAgent{
    baseagent: agent::base_agent::BaseAgent,
    pub initial_msgs: Vec<LLMMessage>,

}


impl TraeAgent {
    fn new(
        base_agent: agent::base_agent::BaseAgent
    ) -> Self{
        TraeAgent {
            baseagent: base_agent,
            initial_msgs: vec![],
        }
    }
}


impl Agent for TraeAgent{
    fn new_task(
            &mut self,
            task:String,
            args: Option<std::collections::HashMap<String, String>>,
            tool_names: Vec<String>,
        ) -> Result<() , AgentError> {
        todo!()
    }

    async fn run(&mut self) -> Result<AgentExecution, &'static str > {

        let start_time = SystemTime::now();

        let mut msgs = & self.initial_msgs;
        let mut exec_agent = AgentExecution{
            task:self.baseagent.task.clone(),
            steps: vec![],
            final_result: None,
            success: false,
            total_token:None,
            execution_time:0.,
            agent_state:AgentState::IDLE
        };
        let mut step_number = 1u32;

        while self.baseagent.max_step >= step_number{

            let mut step =
                AgentStep::new(step_number, AgentStepState::THINKING);

            let exec_msg = self.baseagent.execute_step(
                &mut step, msgs, &mut exec_agent, None
            ).await;


            if exec_msg.is_err() {
                // consider having error message

                exec_agent.agent_state = AgentState::ERROR;
                step.state = AgentStepState::ERROR;
                if let Err(e) = &exec_msg {
                    step.error = Some(e.to_string());
                }

                self.baseagent.finalize_step(&mut step, &mut msgs.clone(), &mut exec_agent);
                break;
            }

            self.baseagent.finalize_step(&mut step, &mut msgs.clone(), &mut exec_agent);
            if !exec_msg.is_err() && exec_agent.agent_state == AgentState::COMPLETED{
                break;
            }
            step_number += 1;
        }

        if step_number > self.baseagent.max_step && exec_agent.agent_state != AgentState::COMPLETED{
            exec_agent.final_result = Some("Task execution exceeded maximum steps without completion".to_string());
            exec_agent.agent_state=AgentState::ERROR;
        }

        // TODO: close tool implmeentation

        let dur = SystemTime::now()
            .duration_since(start_time)
            .expect("system clock went backwards");
        exec_agent.execution_time = dur.as_secs_f64();


        // TODO: update cli here


        Err("haven't finish the implementation")
    }

}
