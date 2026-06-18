"""Engineering-lab fixture: first 100 primes (implement below marker)."""

# <!-- agentswarm:implement -->
def first_n_primes(count: int) -> list[int]:
    primes: list[int] = []
    candidate = 2
    while len(primes) < count:
        if all(candidate % p != 0 for p in primes):
            primes.append(candidate)
        candidate += 1
    return primes


def main() -> None:
    for value in first_n_primes(100):
        print(value)


if __name__ == "__main__":
    main()

