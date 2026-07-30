# Ask questions about a MySQL database in plain English.
#
# Run it with:  python main.py

import os
from urllib.parse import quote_plus

from dotenv import load_dotenv

from agent import get_answer, get_sql, make_agent


def get_db_uri():
    """Builds the database connection string from the .env file."""
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASS")
    host = os.getenv("DB_HOST")
    name = os.getenv("DB_NAME")

    # Check everything is there before we try to connect, so the error message
    # actually says what is wrong.
    if not user or not password or not host or not name:
        raise SystemExit(
            "Missing database settings. Copy .env.example to .env and fill it in."
        )

    # quote_plus escapes characters like @ in the password. Without it the URI
    # would be split in the wrong place and the connection would fail.
    return f"mysql+pymysql://{user}:{quote_plus(password)}@{host}/{name}"


def main():
    # Loads the .env file so os.getenv can find the values in it.
    load_dotenv()

    if not os.getenv("GROQ_API_KEY"):
        raise SystemExit("GROQ_API_KEY is not set in .env.")

    db_uri = get_db_uri()

    print("Connecting to the database...")
    agent = make_agent(db_uri)

    # The thread id tells the agent which conversation this is. We use the same
    # one every time so it remembers what we already asked.
    config = {"configurable": {"thread_id": "my-session"}}

    print("Ready! Ask a question, or type 'exit' to quit.")

    while True:
        try:
            question = input("\nQuestion: ")

            if question.lower() in ("exit", "quit"):
                print("Goodbye!")
                break

            # Skip empty lines instead of sending them to the model.
            if not question.strip():
                continue

            response = agent.invoke(
                {"messages": [{"role": "user", "content": question}]},
                config,
            )

            # Show the SQL as well as the answer, so we can check the agent
            # actually looked at the right thing.
            for sql in get_sql(response):
                print(f"\nSQL: {sql}")

            print(f"\nAnswer: {get_answer(response)}")

        except KeyboardInterrupt:
            # This happens when you press Ctrl+C.
            print("\nGoodbye!")
            break

        except Exception as e:
            # Print the problem and keep going, so one bad question does not
            # close the program.
            print(f"\nSomething went wrong: {e}")


# This is only True when we run "python main.py" directly. It stops the loop
# from starting when eval.py imports get_db_uri from this file.
if __name__ == "__main__":
    main()
