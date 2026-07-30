# Checks how often the agent gets the right answer.
#
# A demo does not prove much, because the agent can answer the same question
# correctly once and wrongly the next time. So we keep a list of questions with
# a "gold" SQL query that we already checked by hand. For each one we run the
# gold query to get the real answer, then ask the agent the same question in
# English. If every value from the gold query appears in the agent's answer, we
# count it as correct.
#
# Run it with:
#   python eval.py       (all the questions)
#   python eval.py 3     (only the first 3, for a quick check)

import json
import sys
import time
from decimal import Decimal

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from agent import get_answer, get_sql, make_agent
from main import get_db_uri

# How long to wait between questions, so we stay under the rate limit.
SLEEP_SECONDS = 5

# If the model says we asked too fast, wait and ask the same question again.
# The wait doubles each time: 20 seconds, then 40.
MAX_TRIES = 3
RETRY_SECONDS = 20

# The free plan also limits how many tokens we can use per day. Once that runs
# out, waiting a few seconds does not help, so stop after this many in a row.
MAX_FAILURES_IN_A_ROW = 2


def is_rate_limit(error):
    """True if the model refused because we asked for too much, rather than
    because something is actually broken."""
    message = str(error).lower()
    return "429" in message or "rate limit" in message


def ask_agent(agent, question):
    """Asks the agent one question, trying again if we hit the rate limit."""
    wait = RETRY_SECONDS

    for attempt in range(1, MAX_TRIES + 1):
        try:
            return agent.invoke(
                {"messages": [{"role": "user", "content": question["question"]}]},
                # A different thread id for each question, so the agent cannot
                # remember the answer from the question before. The attempt
                # number is in there too: a try that failed half way still
                # leaves its messages behind, and we do not want the next try
                # to read them and get confused.
                {"configurable": {"thread_id": f"{question['id']}-try{attempt}"}},
            )
        except Exception as e:
            # Only a rate limit is worth trying again. Anything else is a real
            # problem, so let it through on the first go.
            if not is_rate_limit(e) or attempt == MAX_TRIES:
                raise

            print(f"    Rate limited. Waiting {wait}s, then trying again.")
            time.sleep(wait)
            wait *= 2


def answer_is_correct(answer, rows):
    """Checks that every value from the gold query is in the agent's answer."""
    # Lowercase it and take out the commas, so "3,503" matches "3503".
    answer = answer.lower().replace(",", "")

    for row in rows:
        for value in row:
            # MySQL gives back money and SUM() results as Decimal, not float.
            if isinstance(value, (int, float, Decimal)):
                number = float(value)

                # The model might write the same number in different ways, so
                # accept any of them.
                options = {f"{number:.2f}", f"{number:g}"}
                if number == int(number):
                    options.add(str(int(number)))

                if not any(option in answer for option in options):
                    return False

            # Anything else is text, like a country or an artist name.
            elif str(value).strip().lower() not in answer:
                return False

    return True


def main():
    load_dotenv()

    with open("questions.json") as f:
        questions = json.load(f)

    # If a number was typed after the filename, only run that many questions.
    if len(sys.argv) > 1:
        questions = questions[: int(sys.argv[1])]

    db_uri = get_db_uri()

    print("Connecting to the database...")
    agent = make_agent(db_uri)
    engine = create_engine(db_uri)

    print(f"Running {len(questions)} questions.\n")

    correct = 0
    answered = 0
    failures_in_a_row = 0
    results = []

    # "with" makes sure the connection is closed at the end.
    with engine.connect() as connection:
        for i, question in enumerate(questions, start=1):
            # Run the gold query first. It is quick, and if it is broken we
            # find out before spending tokens on the model.
            gold_rows = connection.execute(text(question["gold_sql"])).fetchall()

            try:
                response = ask_agent(agent, question)
            except Exception as e:
                # The agent never got to answer, so this is not a wrong
                # answer. Mark it as skipped, or the score would look worse
                # than the agent really is.
                print(f"[{i}/{len(questions)}] {question['id']} SKIPPED: {e}")
                results.append({
                    "id": question["id"],
                    "question": question["question"],
                    "correct": False,
                    "skipped": True,
                    "error": str(e),
                })

                if is_rate_limit(e):
                    failures_in_a_row += 1
                    if failures_in_a_row >= MAX_FAILURES_IN_A_ROW:
                        print("\nWe are out of tokens, so the rest would fail "
                              "too. Stopping here.")
                        break
                continue

            # It worked, so start counting failures again from zero.
            failures_in_a_row = 0
            answered += 1

            answer = get_answer(response)
            queries = get_sql(response)

            is_correct = answer_is_correct(answer, gold_rows)
            if is_correct:
                correct += 1

            print(f"[{i}/{len(questions)}] {question['id']} "
                  f"{'CORRECT' if is_correct else 'WRONG'}")

            results.append({
                "id": question["id"],
                "question": question["question"],
                # The last query is the one that gave the answer. The ones
                # before it are usually attempts the agent fixed.
                "agent_sql": queries[-1] if queries else None,
                "answer": answer,
                "correct": is_correct,
                "skipped": False,
            })

            # Pause between questions, but not after the last one.
            if i < len(questions):
                time.sleep(SLEEP_SECONDS)

    # Only count the questions the agent really answered. Counting the skipped
    # ones as wrong would blame the agent for our rate limit.
    skipped = sum(1 for r in results if r["skipped"])
    not_run = len(questions) - len(results)

    print(f"\nScore: {correct} out of {answered} answered")

    if skipped:
        print(f"{skipped} skipped (the model would not reply)")
    if not_run:
        print(f"{not_run} never started (we stopped early)")

    with open("results.json", "w") as f:
        json.dump(results, f, indent=2)

    print("Saved the full results to results.json")


if __name__ == "__main__":
    main()
