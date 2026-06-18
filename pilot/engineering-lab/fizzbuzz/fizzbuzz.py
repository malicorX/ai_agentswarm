"""Engineering-lab fixture: FizzBuzz 1..100 (implement below marker)."""

# <!-- agentswarm:implement -->
def fizzbuzz_line(value: int) -> str:
    if value % 15 == 0:
        return "FizzBuzz"
    if value % 3 == 0:
        return "Fizz"
    if value % 5 == 0:
        return "Buzz"
    return str(value)


def main() -> None:
    for value in range(1, 101):
        print(fizzbuzz_line(value))


if __name__ == "__main__":
    main()

