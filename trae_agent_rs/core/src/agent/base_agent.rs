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

use std::collections::HashMap;
use std::error::Error;
use std::vec;

use crate::llm;
use crate::llm_basics::LLMUsage;
use crate::llm_basics::TextContent;
use crate::tools;
use crate::config;
use crate::ContentItem;
use crate::LLMClient;
use crate::LLMMessage;
use crate::LLMResponse;
use crate::Tool;
pub enum AgentStepState{
    THINKING,
    CALLINGTOOL,
    REFLECTING,
    ERROR,
}

pub enum AgentState{
    IDEL,
    RUNNING,
    COMPLETED,
    ERROR,
}


// The follow is an agent base class
// Base agent is a struct for every agnet
// for example: a trae agent should have a base agent & implement the method of 
// the agents
pub struct BaseAgent{

    pub task: String,
    pub execution_record: AgentExecution, //an agent record that save the result
    pub max_step: u32,

    pub llm_client: LLMClient,
    pub tools: Option<Vec<Box<dyn tools::Tool>>>,
    model_config: config::ModelConfig,

}

impl BaseAgent{
    fn new(
        task: String,
        record: AgentExecution, 
        client: LLMClient,
        max_step: u32,
        model_config: config::ModelConfig,
        tools: Option<Vec<Box<dyn tools::Tool>>>,
    ) -> Self{
        BaseAgent { 
            task: task, 
            execution_record: record, 
            llm_client: client, 
            model_config: model_config, 
            max_step: max_step, 
            tools: tools, 
        }
    }
} 


// this struct should be private Agent 
pub struct AgentExecution {
    task: String, 
    steps: Vec<AgentStep>,
    final_result: Option<String>, 
    success: bool,
    total_token: Option<LLMUsage>,
    execution_time: f64,
    agent_state: AgentState
} 


impl AgentExecution{
    fn new (
        task: String,
        steps: Option<Vec<AgentStep>>,
    ) -> Self{
        AgentExecution { 
            task: task, 
            steps: match steps {
                None => vec![],
                Some(t)=>t,
            }, 
            final_result: None, 
            success: false, 
            total_token: None, 
            execution_time: 0.0, 
            agent_state: AgentState::IDEL, 
        } 
    }
}

// the execution of that specific step
pub struct AgentStep{
    pub step_number: u32,

    pub state:AgentStepState,
    pub thought: Option<String>,

    pub llm_response: Option<LLMResponse>,
    pub tool_calls: Option<Vec<Box <dyn Tool>>>, 

} 

impl AgentStep {
    pub fn new(step_number: u32, state: AgentStepState)-> Self{
        AgentStep { 
            step_number: step_number, 
            state: state, 
            thought: None,
            llm_response: None,
            tool_calls: None,
        }
    }
}


pub trait Agent{
    // run is correspoinding to execute_task in python. 
    fn run(&mut self) -> Result<AgentExecution, &'static str >; 
    fn new_task(
        &mut self, 
        task:String, 
        args: Option<HashMap<String, String>>,
        tool_names: Vec<String>,
    ) -> Result<() , &'static str>;
}


impl BaseAgent{
    // this function correspond to _run_llm_step in the python code
    pub async fn execute_step(
        &mut self, 
        step:&mut AgentStep,
        msgs: Vec<LLMMessage>,
        exec:&mut AgentExecution,

        is_task_complete: Option<Box<dyn FnOnce(&LLMResponse) -> bool>>,

    ) -> Result<Vec<LLMMessage> , &'static str>{

        let msgs_backup = msgs.clone(); // this is not good practice once chat rely only &msgs it should be removed 

        step.state = AgentStepState::THINKING;
        // a cli api should place here currently there's not cli api

        let response = self.llm_client.chat(
            msgs, 
            &self.model_config ,
            None,
            false,
        ).await;

        let llm_response= match response{
            Ok(t) => Some(t),
            Err(e) => {
                Some(LLMResponse { 
                    content: vec![ContentItem::Text(TextContent{text:"error occur for llm responses".to_string()})], 
                    usage: Some(LLMUsage{
                        input_tokens: 0,
                        output_tokens: 0,
                        cache_creation_input_tokens: 0,
                        cache_read_input_tokens: 0,
                        reasoning_tokens: 0,
                    }), 
                    model: Some(self.llm_client.get_provider_name().to_string()), 
                    finish_reason: llm::FinishReason::Error, 
                    tool_calls: None,
                    }
                )
            } 
        };

        step.llm_response = llm_response.clone();         

        let unwrap_response = llm_response.as_ref().expect("It should never be None");
        // update console 
        // update llm usage


        // indicate task complete here
        if indicate_task_complete(&unwrap_response){

            let check_complete: Box<dyn FnOnce(&LLMResponse) -> bool> = match is_task_complete {
                Some(f) => f,
                None => Box::new(|_x| true), // always true if no function is given
            };



            if check_complete(&unwrap_response){
                exec.agent_state = AgentState::COMPLETED;

                let result = unwrap_response
                    .content
                    .get(0)
                    .and_then(|c| c.as_text())
                    .unwrap_or("Error: no message found");

                exec.final_result = Some(result.to_string());
                exec.success = true;
                return Ok(msgs_backup);
            }

            exec.agent_state = AgentState::RUNNING;
            return Ok(
                vec![
                    LLMMessage{
                        role: llm::MessageRole::User,
                        content: None,// TODO !,
                        tool_call: None,
                        tool_result: None
                    }
                ]
            ) // return type here
        }


        let tool_call = &unwrap_response.tool_calls;
        
//        self.tool_call_handler(tool_call,step)

        todo!()
    }


    fn tool_call_handler(
        &mut self, 
        tool_calls: &Option<Vec<Box<dyn Tool>>>, 
        step: &mut AgentStep,
    )  ->  Result<Vec<LLMMessage> , &'static str>
    {


        let unfinished_message = vec![
                    LLMMessage{
                        role:llm::MessageRole::User,
                        content:None, // implement content here
                        tool_call:None,
                        tool_result:None,
                    }
                ];
        
        match tool_calls {
            Some(tools) => {
                if tools.len() == 0 {
                    return Ok(unfinished_message)
                }
                
                step.state = AgentStepState::CALLINGTOOL;

                // console work here TODO

                // TODO need to handle tool call ?

                // handle tool caller_sequential_tool_call
               todo!("we need to finish tool call first") ;

                Ok(unfinished_message)
            },
            None => Ok(unfinished_message)
        }
    }

}




fn indicate_task_complete(response: &LLMResponse)-> bool{
    
    let content = response
        .content
        .get(0)
        .and_then(|c| c.as_text())
        .unwrap_or("Error: can not get the response");

    let completion_indicators = [
        "task completed",
        "task finished", 
        "done", 
        "completed successfully",
        "finished successfully",
    ];

    for _i in 0..completion_indicators.len(){
        if content.contains(completion_indicators[_i]) {
            return true;
        }
    }

    false

}