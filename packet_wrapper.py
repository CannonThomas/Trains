#!/usr/bin/env python3

import sys
import select
import pkt_send

pkt = pkt_send.lib

def main():
    if pkt.initialize() == -1:
        print("GPIO/PIO init failed")
        return 1

    print("************** RP1 PIO DCC INITIALIZED ***************")
    print("Commands:")
    print("  forward")
    print("  backward")
    print("  stop")
    print("  function")
    print("  term")
    print("If no command is typed, it sends idle packets forever.")

    epoll = select.epoll()
    epoll.register(sys.stdin, select.EPOLLIN)

    try:
        while True:
            events = epoll.poll(0)

            if events:
                text_input = sys.stdin.readline().strip()
                print(text_input)

                if "term" in text_input:
                    print("************** TERMINATING ***************")
                    pkt.terminate()
                    return 0

                elif "forward" in text_input:
                    print("sending forward")
                    pkt.forward(5)

                elif "backward" in text_input:
                    print("sending backward")
                    pkt.backward(5)

                elif "stop" in text_input:
                    print("sending stop")
                    pkt.stop(5)

                elif "function" in text_input:
                    print("sending function 1")
                    pkt.function(5, 1)

            # Match previous group style:
            # continuously send idle if no command
            pkt.idle(1)

    except KeyboardInterrupt:
        pkt.terminate()
        return 0

if __name__ == "__main__":
    sys.exit(main())