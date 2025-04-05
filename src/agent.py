from __future__ import annotations

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing import Annotated, Sequence
from typing_extensions import TypedDict

from typing import Literal

from langchain import hub
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from sqlmodel import Field
from settings import get_settings, SUPREME_COURT_CASE_COLLECTION
from langchain_qdrant import QdrantVectorStore
from langchain_openai import OpenAIEmbeddings
from langgraph.graph import END, StateGraph, START
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt import tools_condition
from langchain_core.documents import Document

from functools import partial
from typing import Optional

from pydantic import BaseModel

from langchain_core.callbacks import Callbacks
from langchain_core.prompts import (
    BasePromptTemplate,
    aformat_document,
    format_document,
)
from langchain_core.retrievers import BaseRetriever
from langchain_core.tools.simple import Tool


class RetrieverInput(BaseModel):
    """Input to the retriever."""

    query: str = Field(description="query to look up in retriever")


class AgentResponse(BaseModel):
    """Assistant response with reference court document number if any"""

    response: str = Field(description="final answer")
    court_document_sources: list[str] = Field(
        description=(
            "list of `Nomor Dokumen Putusan` which become reference to answer the "
            "question. Must be exist in the given context, DO NOT make this up"
        )
    )


def _get_relevant_documents(
    query: str,
    retriever: BaseRetriever,
    document_prompt: BasePromptTemplate,
    document_separator: str,
    callbacks: Callbacks = None,
) -> str:
    docs = retriever.invoke(query, config={"callbacks": callbacks})
    unique_docs_number = []
    unique_docs = []

    for doc in docs:
        if doc.metadata["decision_number"] in unique_docs_number:
            continue

        full_summary = doc.metadata["full_summary"]
        decision_number = doc.metadata["decision_number"]
        unique_docs.append(
            Document(
                page_content=f"Nomor Dokumen Putusan: {decision_number}\n\n{full_summary}",
                metadata={"decision_doc_id": doc.metadata["decision_number"]},
            )
        )
        unique_docs_number.append(doc.metadata["decision_number"])

    return document_separator.join(
        format_document(doc, document_prompt) for doc in unique_docs
    )


async def _aget_relevant_documents(
    query: str,
    retriever: BaseRetriever,
    document_prompt: BasePromptTemplate,
    document_separator: str,
    callbacks: Callbacks = None,
) -> str:
    docs = await retriever.ainvoke(query, config={"callbacks": callbacks})
    unique_docs_number = []
    unique_docs = []

    for doc in docs:
        if doc.metadata["decision_number"] in unique_docs_number:
            continue

        full_summary = doc.metadata["full_summary"]
        decision_number = doc.metadata["decision_number"]
        unique_docs.append(
            Document(
                page_content=f"Nomor Dokumen Putusan: {decision_number}\n\n{full_summary}",
                metadata={"decision_doc_id": doc.metadata["decision_number"]},
            )
        )

        unique_docs_number.append(doc.metadata["decision_number"])

    return document_separator.join(
        [await aformat_document(doc, document_prompt) for doc in unique_docs]
    )


def create_retriever_tool(
    retriever: BaseRetriever,
    name: str,
    description: str,
    *,
    document_prompt: Optional[BasePromptTemplate] = None,
    document_separator: str = "\n\n",
) -> Tool:
    """Create a tool to do retrieval of documents.

    Args:
        retriever: The retriever to use for the retrieval
        name: The name for the tool. This will be passed to the language model,
            so should be unique and somewhat descriptive.
        description: The description for the tool. This will be passed to the language
            model, so should be descriptive.
        document_prompt: The prompt to use for the document. Defaults to None.
        document_separator: The separator to use between documents. Defaults to "\n\n".

    Returns:
        Tool class to pass to an agent.
    """
    document_prompt = document_prompt or PromptTemplate.from_template("{page_content}")
    func = partial(
        _get_relevant_documents,
        retriever=retriever,
        document_prompt=document_prompt,
        document_separator=document_separator,
    )
    afunc = partial(
        _aget_relevant_documents,
        retriever=retriever,
        document_prompt=document_prompt,
        document_separator=document_separator,
    )
    return Tool(
        name=name,
        description=description,
        func=func,
        coroutine=afunc,
        args_schema=RetrieverInput,
    )


embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
vector_store = QdrantVectorStore.from_existing_collection(
    embedding=embeddings,
    collection_name=SUPREME_COURT_CASE_COLLECTION,
    path=get_settings().qdrant_filepath,
)

retriever_tool = create_retriever_tool(
    vector_store.as_retriever(search_kwargs={"k": 10}),
    "retrieve_court_decision_document_summary",
    "Search and return information about court decision document in Bahasa "
    "Indonesia",
)

tools = [retriever_tool]


class AgentState(TypedDict):
    # The add_messages function defines how an update should be processed
    # Default is to replace. add_messages says "append"
    messages: Annotated[Sequence[BaseMessage], add_messages]


### Edges


async def grade_documents(state) -> Literal["generate", "rewrite"]:
    """
    Determines whether the retrieved documents are relevant to the question.

    Args:
        state (messages): The current state

    Returns:
        str: A decision for whether the documents are relevant or not
    """

    print("---CHECK RELEVANCE---")

    # Data model
    class grade(BaseModel):
        """Binary score for relevance check."""

        binary_score: str = Field(description="Relevance score 'yes' or 'no'")

    # LLM
    model = ChatOpenAI(temperature=0, model="gpt-4o-mini-2024-07-18")

    # LLM with tool and validation
    llm_with_tool = model.with_structured_output(grade)

    # Prompt
    prompt = PromptTemplate(
        template="""You are a grader assessing relevance of a retrieved document to a user question. \n
        Here is the retrieved document: \n\n {context} \n\n
        Here is the user question: {question} \n
        If the document contains keyword(s) or semantic meaning related to the user question, grade it as relevant. \n
        Give a binary score 'yes' or 'no' score to indicate whether the document is relevant to the question.""",
        input_variables=["context", "question"],
    )

    # Chain
    chain = prompt | llm_with_tool

    messages = state["messages"]
    last_message = messages[-1]

    question = messages[0].content
    docs = last_message.content

    scored_result = await chain.ainvoke({"question": question, "context": docs})

    score = scored_result.binary_score

    if score == "yes":
        print("---DECISION: DOCS RELEVANT---")
        return "generate"

    else:
        print("---DECISION: DOCS NOT RELEVANT---")
        print(score)
        return "rewrite"


### Nodes


async def agent(state):
    """
    Invokes the agent model to generate a response based on the current state. Given
    the question, it will decide to retrieve using the retriever tool, or simply end.

    Args:
        state (messages): The current state

    Returns:
        dict: The updated state with the agent response appended to messages
    """
    print("---CALL AGENT---")
    messages = state["messages"]
    model = ChatOpenAI(temperature=0, model="gpt-4o-mini-2024-07-18")
    model = model.bind_tools(tools)
    result = await model.ainvoke(messages)

    return {"messages": [result]}


async def rewrite(state):
    """
    Transform the query to produce a better question.

    Args:
        state (messages): The current state

    Returns:
        dict: The updated state with re-phrased question
    """

    print("---TRANSFORM QUERY---")
    messages = state["messages"]
    question = messages[0].content

    msg = [
        HumanMessage(
            content=f""" \n
    Look at the input and try to reason about the underlying semantic intent / meaning. \n
    Here is the initial question:
    \n ------- \n
    {question}
    \n ------- \n
    Formulate an improved question: """,
        )
    ]

    # Grader
    model = ChatOpenAI(temperature=0, model="gpt-4o-mini-2024-07-18")
    response = await model.ainvoke(msg)
    return {"messages": [response]}


async def generate(state):
    """
    Generate answer

    Args:
        state (messages): The current state

    Returns:
         dict: The updated state with re-phrased question
    """
    print("---GENERATE---")
    messages = state["messages"]
    question = messages[0].content
    last_message = messages[-1]

    docs = last_message.content

    # Prompt
    prompt = hub.pull("rlm/rag-prompt")
    prompt.messages[0].prompt.template = """
You are an assistant for court decision document question-answering tasks.
Use the following pieces of retrieved context to answer the question.

# Question

{question}

# Contexts

{context}

# Rules

- If you don't know the answer, just say that you don't know. DON'T make up the answer
- Keep the answer as concise as possible
- Always answer in Bahasa Indonesia
- If formatting is necessary, always use Markdown with Commonmark style formatting in
    the response
- ALWAYS return the related reference `Nomor Dokumen Putusan` if the generated answer
    utilize information from the contexts

# Answer
"""

    # LLM
    llm = ChatOpenAI(model_name="gpt-4o-mini-2024-07-18", temperature=0)
    structured_llm = llm.with_structured_output(AgentResponse)

    # Chain
    rag_chain = prompt | structured_llm

    # Run

    result = await rag_chain.ainvoke({"context": docs, "question": question})
    references = result.court_document_sources
    response = result.response
    if references:
        response += f"\n\nReferensi:\n\n{references}"

    return {
        "messages": [
            AIMessage(content=response, additional_kwargs={"references": references})
        ]
    }


def get_workflow():
    # Define a new graph
    workflow = StateGraph(AgentState)

    # Define the nodes we will cycle between
    workflow.add_node("agent", agent)  # agent
    retrieve = ToolNode([retriever_tool])
    workflow.add_node("retrieve", retrieve)  # retrieval
    workflow.add_node("rewrite", rewrite)  # Re-writing the question
    workflow.add_node(
        "generate", generate
    )  # Generating a response after we know the documents are relevant
    # Call agent node to decide to retrieve or not
    workflow.add_edge(START, "agent")

    # Decide whether to retrieve
    workflow.add_conditional_edges(
        "agent",
        # Assess agent decision
        tools_condition,
        {
            # Translate the condition outputs to nodes in our graph
            "tools": "retrieve",
            END: END,
        },
    )

    # Edges taken after the `action` node is called.
    workflow.add_conditional_edges(
        "retrieve",
        # Assess agent decision
        grade_documents,
    )
    workflow.add_edge("generate", END)
    workflow.add_edge("rewrite", "agent")

    return workflow
