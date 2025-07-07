from trae_agent.utils.local_client import LocalClient
from trae_agent.utils.config import ModelParameters
from trae_agent.utils.llm_basics import LLMMessage

def test_local_client():
    model_parameters = ModelParameters(
        model="Qwen2.5-72B-Instruct",
        base_url="http://192.168.81.79:7142/v1",
        api_key="EMPTY",
        max_tokens=1000,
        temperature=0.5,
        top_p=1,
        top_k=0,
        parallel_tool_calls=False,
        max_retries=3,
    )

    client = LocalClient(model_parameters)

    user_send_message = "Hello, how are you?"

    response = client.chat(
        messages=[
            LLMMessage(role="user", content=user_send_message)
        ],
        model_parameters=model_parameters,
    )
    print(response.content)


if __name__ == "__main__":
    test_local_client()