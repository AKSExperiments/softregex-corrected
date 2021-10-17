import asyncio
import websockets

PORT = 8080

print("Started on:" + str(PORT))
modelClient = ""
connected = set()


async def echo(websocket, path):
    print("Client Connected")
    try:
        async for message in websocket:
            if message == "type:model":
                global modelClient
                modelClient = websocket
            elif message == "type:client":
                connected.add(websocket)
            elif websocket in connected:
                print(str(id(websocket)) + ":" + message)
                await modelClient.send(str(id(websocket)) + ":" + message)
            elif modelClient == websocket:
                print(message)
                message_arr = message.split(":", 1)
                client = message_arr[0]
                for conn in connected:
                    if str(id(conn)) == client:
                        await conn.send(message_arr[1])
    except websockets.exceptions.ConnectionClosed as e:
        print("A client disconnected")
        print(e)
    finally:
        connected.remove(websocket)

start_server = websockets.serve(echo, "0.0.0.0", PORT)
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()
