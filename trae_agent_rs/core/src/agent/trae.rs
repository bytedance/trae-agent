// the implementation of trae agent

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
    initial_msgs: Vec<LLMMessage>,

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
        ) -> Result<() , &'static str> {
        todo!()
    }

    fn run(&mut self) -> Result<AgentExecution, &'static str > {

        let start_time = SystemTime::now();

        let mut msgs = &mut self.initial_msgs;
        let mut step_number = 1u32;

        while self.baseagent.max_step >= step_number{

            let step = 
                AgentStep::new(step_number, AgentStepState::THINKING);


        }



        Err("havne't finish the implementation")
    }

}