#!/usr/bin/env python

"""
This example demonstrates how to use async IO with python-can.
"""

import asyncio
from typing import List

import can
from can.notifier import MessageRecipient


# can.rc['interface'] = 'socketcan'
# can.rc['channel'] = 'can0'
# can.rc['bitrate'] = 500000

def print_message(msg: can.Message) -> None:
    """Regular callback function. Can also be a coroutine."""
    print(msg)


async def main() -> None:
    """The main function that runs in the loop."""

    print("testing")

    with can.Bus(  # type: ignore
        interface="socketcan", channel="can0", bitrate=5000000
    ) as bus:
        reader = can.AsyncBufferedReader()
        # logger = can.Logger("logfile.asc")

        listeners: List[MessageRecipient] = [
            print_message,  # Callback function
            reader,
            # logger,
        ]
        # Create Notifier with an explicit loop to use for scheduling of callbacks
        loop = asyncio.get_running_loop()
        notifier = can.Notifier(bus, listeners, loop=loop)
        # Start sending first message
        # bus.send(can.Message(arbitration_id=0))

        print("Reading messages...")
        while True:
            msg = await reader.get_message()

        # Wait for last message to arrive
        await reader.get_message()
        print("Done!")

        # Clean-up
        notifier.stop()


if __name__ == "__main__":
    asyncio.run(main())