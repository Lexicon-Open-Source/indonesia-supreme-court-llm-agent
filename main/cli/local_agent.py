import typer
from utility.runtime import coroutine_wrapper
from langgraph.checkpoint.memory import MemorySaver
from src.agent import get_workflow


app = typer.Typer()


@app.command()
@coroutine_wrapper
async def main():
    checkpointer = MemorySaver()
    agent_workflow = get_workflow()
    agent_graph = agent_workflow.compile(checkpointer=checkpointer)

    try:
        while True:
            user_input = input("User: ")
            if user_input.lower() in ["quit", "exit", "q"]:
                print("Goodbye!")
                break

            graph_run_config = {
                "configurable": {
                    # langgraph standard for session/thread id
                    "thread_id": 1,
                    "user_id": 1,  # langgraph standard for user id
                },
            }
            user_input = {
                "messages": [("user", user_input)],
            }

            agent_graph_state = await agent_graph.ainvoke(user_input, graph_run_config)

            ai_response = agent_graph_state["messages"][-1]
            response = str(ai_response.content)

            if "references" in ai_response.additional_kwargs:
                references = ai_response.additional_kwargs["references"]
                response += f"\n\nReferences: {references}"

            print(f"Assistant: {response}")
    finally:
        # Uncomment this if using PostgreSQL checkpoint saver
        pass


if __name__ == "__main__":
    app()
