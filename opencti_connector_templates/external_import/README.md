# External import connector

## Usage

Subclass the `ExternalImportConnector` and overwrite the `_collect_intelligence` function:

```python
from opencti_connector_templates import ExternalImportConnector

class MyConnector(ExternalImportConnector):

    def __init__(self):
        super().__init__()
        # Get any extra environment variables
        self.feed_name = self._get_env("FEED_NAME")  # Required
        self.feed_auth = self._get_env("FEED_AUTH", None)  # Optional

    def _collect_intelligence(self) -> list[stix2.base._STIXBase]:
        """Collects intelligence and returns STIX2 objects"""
        return [
            stix2.IPV4Address(value="8.8.8.8"),
            stix2.IPV4Address(value="8.8.4.4"),
        ]
```

## Advanced usage

### Saving state

The class variable `current_status` is a dictionary that is stored within the OpenCTI environment. It allows you to save state between runs. Before each run of `_collect_intelligence` it is retrieved and after each run it is saved. 

It might be useful to keep track of the latest changes that were handled by storing a date/time:

```python
# Get latest known id
last_item_id = self.current_status.get("last_item_id", 0)
# Retrieve new data
stix_data = get_intelligence(since=last_item_id)
# Store latest id
self.current_status["last_item_id"] = stix_data[-1]['id']
# Return data
return stix_data
```