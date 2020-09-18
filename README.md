Splunk HEC for Home Assistant

Requires you create an aiohttp Client Session, or reuse your existing one from `homeassistant.helpers.aiohttp_client.async_get_clientsession`

~~~~{.python}
import asyncio
import aiohttp
from hass_splunk import hass_splunk

async def main():
    async with aiohttp.ClientSession() as session:
        splunk = hass_splunk(session=session,host="192.168.1.1",use_ssl=True,verify_ssl=False,token="private")
        print(await splunk.check(connectivity=True, token=True, busy=True))
        await splunk.queue({
                "time": 0,
                "host": "name",
                "event": {
                    "meta": "TEST",
                },
            },send=False)
        await splunk.send()
asyncio.run(main())
~~~~