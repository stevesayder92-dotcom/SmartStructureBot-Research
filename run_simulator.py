from simulator.cli import main


if __name__ == "__main__":
    raise SystemExit(main(["serve", *(__import__("sys").argv[1:])]))

