

# OpenCTI Connector templates

This repository contains modified versions of the OpenCTI Connector templates that can be found on their Github: https://github.com/OpenCTI-Platform/connectors in the `templates/`-folder.

It aims to correct some issues that are found in the default templates and provide a PyPi package for easy re-use in other implementations and make writing integrations easier.


## Installation

Easiest is to add the following to your `pyproject.toml` or `requirements.txt`:

`opencti_connector_templates @ git+ssh://git@git.ciso.lan/cert/threat-intelligence/opencti-connector-templates.git@main`

Alternatively, build and install the package locally:

```bash
python3 -m pip install flit
flit install
```

## Issues

### Overall

 - Unclear usage of environment variables (mostly caused by the underlying `pycti` package)


### External Import

 - Logging is too verbose and in an unclear format.
 - Empty result sets throw an exception