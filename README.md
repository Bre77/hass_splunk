# Splunk HEC for Home Assistant

A Splunk HTTP Event Collector library that follows best practices by opening a single connection to Splunk, and reuses it. When sending large or high volumes of events, or Splunk is slow, the events are batched together. This also allows events to be resent in the case of failures, as they are simply returned to the queue.

Requires you create an aiohttp Client Session, or reuse your applications existing one. From Home Assistant this would be `homeassistant.helpers.aiohttp_client.async_get_clientsession`

## Methods

### hass_splunk(session,token,host,port=8088,use_ssl=True,verify_ssl=True,endpoint="collector/event",timeout=5)

Session, token, and host are required, all other parameters are optional, and will be set to defaults shown.

### check(connectivity=True, token=True, busy=True)

Returns True if the parameter conditions are okay, False if any fail or any other error is raised. You can selectively ignore certain conditions by setting them to False.

### queue(payload, send=True)

The String or Dictionary to be sent to Splunk. By default it will be sent as soon as possible, but you can instead set send=False and it only be queued.

### send()

The sends whatever data is in the queue, is what queue() uses internally when send=True.

## Example

```{.python}
import asyncio
import aiohttp
import time
from hass_splunk import hass_splunk


async def main():
    async with aiohttp.ClientSession() as session:
        splunk = hass_splunk(
            session=session,
            host="http-inputs-stack.splunkcloud.com",
            use_ssl=True,
            verify_ssl=True,
            token="private",
        )
        print(await splunk.check(connectivity=True, token=True, busy=True))
        await splunk.queue(
            {
                "time": time.time(),
                "host": "name",
                "event": {
                    "meta": "TEST",
                },
            },
            send=False,
        )
        await splunk.send()

asyncio.run(main())
```
