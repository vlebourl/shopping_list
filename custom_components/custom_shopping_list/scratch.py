import asyncio

from bring import BringApi

loop = asyncio.get_event_loop()
api = BringApi("vlebourl@gmail.com", "qTJ4zcTitu9LWb")
loop.run_until_complete(api.login())
loop.run_until_complete(api.get_lists())

api.select_list("Maison")


print("logged in")
