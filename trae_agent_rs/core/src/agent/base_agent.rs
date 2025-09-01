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

// The follow is an agent base class
pub struct Agent{
    llm_client: Box<dyn llm::LLMProvider>,
    max_step: u32,

    task: String, 
    

}


