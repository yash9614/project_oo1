from assistant.pipeline import Assistant

assistant = Assistant()

for username in ("alice", "bob"):
    print(f"\n===== {username} =====")
    answer = assistant.ask("Who may push to production?", username)
    print(f"Answered: {answer.answered} | Grounded: {answer.fully_grounded}")
    print(answer.text)
    for line in answer.trace:
        print("  ", line)