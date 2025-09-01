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

use crate::llm;
use crate::tools;
use crate::config;

// The follow is an agent base class
// Base agent is a struct for every agnet
// for example: a trae agent should have a base agent & implement the method of 
// the agents
pub struct BaeAgent{

    pub task: String,
    pub execution_record: AgentRecord, //an agent record that save the result

    llm_client: Box<dyn llm::LLMProvider>,
    model_config: config::ModelConfig,
    max_step: u32,
    tools: Vec<Box<dyn tools::Tool>>,



}

struct AgentRecord {

} 


pub trait Agent{
    fn run(&mut self) -> AgentRecord;
}