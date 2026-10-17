from assistant.repository import connection, find_user

with connection() as conn:
    alice = find_user(conn, "alice")
    bob = find_user(conn, "bob")
    unknown = find_user(conn, "hacker")

print(alice)
print(alice.describe_access())
print(bob.describe_access())
print(unknown.describe_access())