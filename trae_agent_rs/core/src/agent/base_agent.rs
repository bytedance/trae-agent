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

use thiserror::Error;
use std::collections::HashMap;
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
use crate::ToolCall;
use crate::ToolResult;
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
    pub tools: Option<HashMap<String ,Box<dyn tools::Tool>>>,
    model_config: config::ModelConfig,

}

impl BaseAgent{
    fn new(
        task: String,
        record: AgentExecution, 
        client: LLMClient,
        max_step: u32,
        model_config: config::ModelConfig,
        tools: Option<HashMap<String,Box<dyn tools::Tool>>>,
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
    pub tool_calls: Option<Vec<ToolCall>>, 

    pub tool_results: Option<Vec<Result<String ,String>>>

} 

impl AgentStep {
    pub fn new(step_number: u32, state: AgentStepState)-> Self{
        AgentStep { 
            step_number: step_number, 
            state: state, 
            thought: None,
            llm_response: None,
            tool_calls: None,
            tool_results: None,
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
                        content: None,// TODO:  task_incomplete_message
                        tool_call: None,
                        tool_result: None
                    }
                ]
            ) // return type here
        }

        let tool_call = &unwrap_response.tool_calls;
        let val =self.tool_call_handler(tool_call,step).await;

        todo!()
    }


    async fn tool_call_handler(
        &mut self, 
        tool_call: &Option<Vec<ToolCall>>,
        step: &mut AgentStep,
    )-> Result<LLMMessage, AgentError>{


        let tool_size = tool_call
            .as_ref()
            .unwrap_or(&vec![])
            .len();

        if tool_size == 0 {
            return Ok(LLMMessage{
                role:llm::MessageRole::User,
                content:Some(vec![ContentItem::text("It seems that you have not completed the task".to_string())]),
                tool_call: None,
                tool_result:None
            })
        }

        step.state = AgentStepState::CALLINGTOOL;

        let default_vec  = vec![];

        let unwrapped_tool = tool_call
            .as_ref()
            .unwrap_or(&default_vec);

        let agent_tools=
            self.tools.get_or_insert_with(HashMap::new);

        let mut tool_results = vec![];
        
        // TODO: parallel tool call 
        for tool in unwrapped_tool{
            let result = match tool.name.as_str() {
                "bash" => {
                    // ensure `agent_tools` is a mutable variable in scope: `&mut agent_tools`
                    match agent_tools.get_mut("bash") {
                        Some(x) => 
                        {
                            x.execute(tool.arguments.clone()).await
                        },
                        None => Err("Cannot find bash tool".to_string()),
                    }
                },
                
                "str_replace_based_edit_tool" => {
                        match agent_tools.get_mut("str_replace_based_edit_tool") {
                            Some(x) => x.execute(tool.arguments.clone()).await,
                            None => Err("Cannot find str_replace_based_edit tool".to_string()),
                    } 
                }
                _ => Err("The requested tool is not found".to_string()),
            };

            tool_results.push(result);
        }
        
        step.tool_results = Some(tool_results.clone());

        let mut msg:Vec<LLMMessage> = Vec::new();

        for tool_result in tool_results{

        }


        todo!()
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

#[derive(Error, Debug)]
pub enum AgentError {
    #[error("Internal Error {0}")]
    InternalError(String) 
}

fn execresult_to_toolresult(
    execresult: Result<String, String>, 
)-> String{

    "".to_string()
}