# Natural Language SQL Agent

Ask questions about a MySQL database in plain English. The agent looks at the
database, writes the SQL itself, runs it, and answers in a sentence.

```
Question: how many albums does Iron Maiden have?

SQL: SELECT COUNT(*) FROM Album al JOIN Artist ar ON al.ArtistId = ar.ArtistId
     WHERE ar.Name = 'Iron Maiden'

Answer: Iron Maiden has 21 albums.
```

## How it works

The agent runs in a loop instead of answering in one step:


1. It gets a question and a set of tools.
2. It picks a tool, we run it, and we give it the result.
3. It repeats until it knows the answer.

It has four tools, which come from LangChain's `SQLDatabaseToolkit`:

| Tool | What it does |
|------|--------------|
| `sql_db_list_tables` | lists the tables |
| `sql_db_schema` | shows the columns of a table |
| `sql_db_query_checker` | checks the SQL looks valid |
| `sql_db_query` | runs the SQL |

Letting it read the real schema is what stops it inventing table names, which
is the most common way these agents go wrong.

## Files

| File | What it is |
|------|------------|
| `agent.py` | builds the agent |
| `main.py` | the program you run to ask questions |
| `eval.py` | measures how often the agent is right |
| `questions.json` | 13 test questions with correct SQL |

## Setup

You need MySQL with the [Chinook](https://github.com/lerocha/chinook-database)
sample database loaded, and a free API key from
[Groq](https://console.groq.com/keys).

```bash
pip install -r requirements.txt
cp .env.example .env      # then fill in your password and API key
python main.py
```

Type `exit` to quit. It remembers the conversation, so follow-up questions like
"and which one is second?" work.

## Measuring it

A demo does not prove much, because the agent can answer the same question
right once and wrong the next time. So `eval.py` asks 13 questions that have a
correct SQL query written next to them. It runs the correct query, asks the
agent the same question in English, and checks that every value from the
correct answer shows up in what the agent said.

```bash
python eval.py       # all 13 questions
python eval.py 3     # just the first 3
```

It prints a score and writes the full details to `results.json`, so you can
read the SQL the agent wrote for the questions it got wrong.

The last run scored **12 out of 13**, and the `results.json` in this repo is
that run.

The one it misses is q06, "what is the average track length in minutes?". It
writes a correct query and the database hands back 6.56, and then the answer
says something else: 4.05 on one run, 4.27 on the next. So the SQL is right
every time and the number in the sentence is not. `temperature=0` makes the
model steadier but it does not make it exact, which is why the same question
can fail two different ways. This is the same kind of mistake as the top 5
countries one below, and it is the reason the eval checks the answer text
instead of just comparing the SQL.

Checking the answer text, and not just the SQL, matters. The agent once ran a
completely correct query for the top 5 countries by sales and then wrote a
summary listing the United Kingdom instead of Brazil. Brazil is 4th and the UK
is 6th, so the SQL was right and the sentence was wrong, and the sentence is
the part a person actually reads.

## Notes

- The prompt tells the agent to only use `SELECT`, but a prompt is a request,
  not a guarantee. The real protection is giving MySQL a user that can only
  read, which is why `.env.example` sets one up that way.
- The schema is loaded without example rows (`sample_rows_in_table_info=0`).
  Each question costs several model calls and the schema is sent every time,
  so leaving the sample rows in used up the free tokens much faster.
- The conversation is only kept in memory, so it is forgotten when you close
  the program.
