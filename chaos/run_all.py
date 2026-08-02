"""Runs both chaos experiments back to back and prints a combined summary."""

import mttr_experiment
import precision_experiment


def main() -> None:
    print("=== Root-cause precision experiment ===")
    precision_experiment.main()

    print("\n=== MTTR reduction experiment ===")
    mttr_experiment.main()


if __name__ == "__main__":
    main()
