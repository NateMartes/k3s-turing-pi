#!/usr/bin/env python3
import argparse
import time

from lib.k3s_gpu_taints import (
    GPU_RESOURCE, GPU_TAINT_EFFECT, GPU_TAINT_VALUE, gpu_node_names, kubectl,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Taint every discovered NVIDIA GPU node.")
    parser.add_argument(
        "--wait-timeout",
        type=int,
        default=0,
        metavar="SECONDS",
        help="wait up to this many seconds for GPU discovery (default: 0)",
    )
    args = parser.parse_args()
    if args.wait_timeout < 0:
        parser.error("--wait-timeout cannot be negative")

    deadline = time.monotonic() + args.wait_timeout
    while True:
        node_names = gpu_node_names()
        if node_names or time.monotonic() >= deadline:
            break
        time.sleep(2)
    if not node_names:
        print(f"No nodes were discovered with the {GPU_RESOURCE} resource or GPU label.")
        return

    taint = f"{GPU_RESOURCE}={GPU_TAINT_VALUE}:{GPU_TAINT_EFFECT}"
    kubectl("taint", "nodes", *node_names, taint, "--overwrite")
    print(f"Tainted {len(node_names)} GPU node(s): {', '.join(node_names)}")


if __name__ == "__main__":
    main()
