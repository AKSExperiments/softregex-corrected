import websockets
import asyncio
import sys


clientType = sys.argv[1]


async def listen():
    url = "ws://showmeregex.centralus.cloudapp.azure.com:8080"
    async with websockets.connect(url) as ws:
        await ws.send("type:" + clientType)

        while True:
            input_string = await ws.recv()
            print("Input string: ", input_string)
            input_str_arr = input_string.split(":", 1)
            client = input_str_arr[0]
            input_string = input_str_arr[1]
            await ws.send(client + ":out")


asyncio.get_event_loop().run_until_complete(listen())