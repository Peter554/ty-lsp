import argparse

from . import _core


def main():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("a", type=int)
    arg_parser.add_argument("b", type=int)
    args = arg_parser.parse_args()

    print(_core.add(args.a, args.b))
