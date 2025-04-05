from collections.abc import Callable
from typing import Literal

import litellm
from langchain_community.chat_models.litellm import ChatLiteLLM
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.messages.utils import convert_to_openai_messages
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from litellm.exceptions import (
    APIConnectionError,
    APIError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)
from litellm.types.utils import Message
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


@retry(
    retry=retry_if_exception_type(
        (
            Timeout,
            RateLimitError,
            APIConnectionError,
            APIError,
            ServiceUnavailableError,
        )
    ),
    wait=wait_exponential(multiplier=1, min=5, max=10),
    stop=stop_after_attempt(5),
    reraise=True,
)
async def call_model(
    messages: list[type[BaseMessage]],
    model_conf: dict,
    tools: list[Callable | BaseTool | BaseModel] | None = None,
    system_prompt: str | None = None,
    enable_tracing: bool = False,
    tracing_metadata: dict | None = None,
    response_format: Literal["litellm", "langchain"] = "litellm",
    return_full_response: bool = False,
) -> AIMessage | Message | str:
    """
    Generates a response from the specified language model based on the
    provided messages and configuration.

    Args:
        messages (list[type[BaseMessage]]):
            A list of messages representing the conversation history.
        model_conf (dict):
            Litellm model configurations, to handle various model api key or credential
            settings.
        tools (list[Callable | BaseTool | BaseModel], optional):
            A list of tool functions that the model can utilize.
            Defaults to [].
        system_prompt (str | None, optional):
            An optional system prompt to provide context to the model.
            Defaults to None.
        enable_tracing (bool, optional):
            Flag to enable tracing for the model invocation. Defaults to False.
        tracing_metadata (dict | None, optional):
            Metadata to include when tracing is enabled, see details
            https://docs.litellm.ai/docs/observability/langfuse_integration.
            Defaults to {}.
        response_format (Literal["litellm", "langchain"], optional):
            The format of the response. Choose between "litellm" and "langchain".
            Defaults to "litellm".
        return_full_response (bool, optional):
            If set True, will return all response metadata

    Returns:
        AIMessage | Message | str: The response generated by the language model.
    """
    if tracing_metadata is None:
        tracing_metadata = {}

    chat_prompts = []

    if system_prompt:
        # this is similar to customizing the create_react_agent with state_modifier, but
        # is a lot more flexible
        # Notes that system prompt is not embedded in chat history
        chat_prompts = [SystemMessage(content=system_prompt)]

        # o1 model not support system prompt
        if model_conf["model"].startswith("o1"):
            chat_prompts = [HumanMessage(content=system_prompt)]

    chat_prompts.extend(messages)

    # As we're using vanilla litellm sdk, we need to format the langchain message
    # format to openai format
    formatted_chat_prompts = convert_to_openai_messages(chat_prompts)

    if enable_tracing:
        litellm.success_callback = ["langfuse"]
        litellm.failure_callback = ["langfuse"]
    else:
        litellm.success_callback = []
        litellm.failure_callback = []

    # If using function with docstring in the tools, need to remove the type hint from
    # the docstring(PEP484), otherwise will `convert_to_openai_tool` function will raise
    # error
    tools = [convert_to_openai_tool(func) for func in tools] if tools else None

    # Drop unsupported params, E.g unintentionally providing temperature to o1 model
    # (o1 model not support temperature)
    litellm.drop_params = True
    response = await litellm.acompletion(
        messages=formatted_chat_prompts,
        tools=tools,
        metadata=tracing_metadata,
        **model_conf,
    )

    # Let's use Langchain ChatLiteLLM function to reformat the response into langchain
    # format
    if response_format == "langchain":
        response = ChatLiteLLM()._create_chat_result(response)
        if return_full_response:
            return response

        return response.generations[0].message

    if return_full_response:
        return response

    return response.choices[0].message
