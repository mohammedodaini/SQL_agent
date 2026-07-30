# Builds the SQL agent.
#
# The agent works in a loop. We give it some tools and a question, it picks a
# tool, we run it and give back the result, and it picks again until it knows
# the answer. LangGraph runs that loop for us.

from langchain.agents import create_agent
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import InMemorySaver

MODEL = "llama-3.3-70b-versatile"

# The instructions the model reads before every question.
SYSTEM_PROMPT = """You are an agent that answers questions about a MySQL database.

Follow these steps:
1. List the tables, then look at the schema of the ones you need.
2. Write one MySQL SELECT query and run it.
3. Answer in plain English and include the numbers you found.

Never guess a table or column name. Look at the schema first, and join on the
id columns you saw there, not on names.

Never answer from a query you only wrote down. Run it and use what it gives
back. If a query fails, fix it and run it again.

Only use SELECT. Never use INSERT, UPDATE, DELETE or DROP.
"""


def make_agent(db_uri):
    """Creates the agent that answers questions about the database."""
    # sample_rows_in_table_info=0 means the schema does not include example
    # rows. This keeps the prompt smaller so we use fewer tokens.
    db = SQLDatabase.from_uri(db_uri, sample_rows_in_table_info=0)

    # temperature=0 means the model gives the same answer every time instead
    # of a random one. We want that for SQL.
    llm = ChatGroq(model=MODEL, temperature=0)

    # The toolkit gives the agent four tools: list the tables, show a table's
    # schema, check if a query looks valid, and run a query.
    tools = SQLDatabaseToolkit(db=db, llm=llm).get_tools()

    # InMemorySaver saves the conversation, which is what makes follow-up
    # questions work. It is forgotten when the program closes.
    return create_agent(
        model=llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        checkpointer=InMemorySaver(),
    )


def get_answer(response):
    """Gets the final text answer out of the agent's response."""
    content = response["messages"][-1].content

    # Usually it is just a string.
    if isinstance(content, str):
        return content

    # Some models return a list of blocks instead, so join the text ones.
    text = ""
    for block in content:
        if isinstance(block, dict):
            text += block.get("text", "")
    return text.strip()


def get_sql(response):
    """Gets the SQL queries the agent ran for the newest question."""
    messages = response["messages"]

    # The response holds the whole conversation, so find where the newest
    # question starts. Otherwise we would print old queries again.
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].type == "human":
            messages = messages[i:]
            break

    queries = []
    for message in messages:
        # Only the model's messages have tool_calls, so use getattr with a
        # default to avoid an error on the others.
        for call in getattr(message, "tool_calls", None) or []:
            if call["name"] == "sql_db_query":
                queries.append(call["args"]["query"])
    return queries
