"""Windows VM fixture: build hello.exe and run natively (implement below marker)."""

# <!-- agentswarm:implement -->
def greet(name: str) -> str:
    return f"hello {name}"


def main() -> None:
    print(greet("agentswarm"))


if __name__ == "__main__":
    main()

